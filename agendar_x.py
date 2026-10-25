"""
Agendador de posts no X (Playwright)
https://github.com/bruno-cr/agendador-posts-x

Abre o X no navegador, e para cada post do posts.csv que ainda não foi
agendado: anexa o card, coloca a descrição da imagem, escreve o texto,
escolhe data e hora no agendador do X e, depois da sua confirmação,
clica em "Agendar".

Uso:
  python agendar_x.py            agenda os posts pendentes
  python agendar_x.py --direto   agenda sem pedir confirmação a cada post
"""
import asyncio, csv, json, os, re, shutil, subprocess, sys, urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

PASTA = Path(__file__).resolve().parent
ARQ_POSTS = PASTA / "posts.csv"
ARQ_LOG = PASTA / "agendados.json"
PERFIL = PASTA / "perfil_navegador"      # guarda o login entre uma execução e outra
BASE = "https://x.com"
DIRETO = "--direto" in sys.argv
ESPERA = 1.0                              # segundos entre etapas (aumente se o X travar)
PORTA = 9222                              # porta usada para conectar ao Chrome


def achar_chrome():
    candidatos = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        shutil.which("google-chrome") or "", shutil.which("chrome") or "",
    ]
    for c in candidatos:
        if c and os.path.exists(c):
            return c
    sys.exit("Não encontrei o Google Chrome instalado. Instale o Chrome e rode de novo.")


def chrome_aberto():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/json/version", timeout=1)
        return True
    except Exception:
        return False


def abrir_chrome():
    """Abre um Chrome comum (sem marcas de automação) com um perfil só para o X."""
    if chrome_aberto():
        return
    PERFIL.mkdir(exist_ok=True)
    subprocess.Popen([achar_chrome(), f"--remote-debugging-port={PORTA}", f"--user-data-dir={PERFIL}",
                      "--no-first-run", "--no-default-browser-check", f"{BASE}/home"])
    for _ in range(30):
        if chrome_aberto():
            return
        import time; time.sleep(0.5)
    sys.exit("O Chrome não abriu a tempo. Feche todas as janelas desse Chrome e rode de novo.")


# ---------- planilha e registro ----------
def ler_posts():
    if not ARQ_POSTS.exists():
        sys.exit("Arquivo posts.csv não encontrado. Copie posts_exemplo.csv para posts.csv e preencha.")
    with open(ARQ_POSTS, encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f, delimiter=";"))
    posts = []
    for n, l in enumerate(linhas, start=2):
        try:
            quando = datetime.strptime(f'{l["data"].strip()} {l["hora"].strip()}', "%d/%m/%Y %H:%M")
        except (ValueError, KeyError):
            print(f"[aviso] linha {n}: data/hora inválida, ignorada")
            continue
        posts.append({"id": f'{l["data"].strip()} {l["hora"].strip()}', "quando": quando,
                      "imagem": (l.get("imagem") or "").strip(), "texto": (l.get("texto") or "").strip(),
                      "alt": (l.get("descricao_imagem") or "").strip()})
    return sorted(posts, key=lambda p: p["quando"])

def ler_log():
    return json.loads(ARQ_LOG.read_text(encoding="utf-8")) if ARQ_LOG.exists() else {}

def salvar_log(log):
    ARQ_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")

def perguntar(msg):
    return input(msg).strip().lower()


# ---------- ajudantes de página ----------
async def primeiro_visivel(page, seletores, timeout=8000):
    """Devolve o primeiro seletor que aparecer na tela."""
    fim = asyncio.get_event_loop().time() + timeout / 1000
    while asyncio.get_event_loop().time() < fim:
        for s in seletores:
            loc = page.locator(s).first
            try:
                if await loc.is_visible():
                    return loc
            except Exception:
                pass
        await asyncio.sleep(0.3)
    return None

async def etapa(nome, coro):
    """Executa uma etapa; se falhar, deixa você resolver na janela."""
    try:
        await coro
        return True
    except Exception as e:
        print(f"   [!] Não consegui: {nome} ({str(e).splitlines()[0][:120]})")
        r = perguntar("       Faça essa etapa na janela do navegador e aperte Enter "
                      "(ou digite 'p' para pular este post): ")
        return r != "p"


# ---------- etapas do post ----------
async def abrir_compositor(page):
    await page.goto(f"{BASE}/compose/post")
    caixa = await primeiro_visivel(page, ['[data-testid="tweetTextarea_0"]', 'div[role="textbox"]'], 15000)
    if not caixa:
        raise RuntimeError("caixa de texto não apareceu")

async def anexar_imagem(page, caminho):
    await page.locator('input[data-testid="fileInput"], input[type="file"]').first.set_input_files(str(caminho))
    ok = await primeiro_visivel(page, ['[data-testid="attachments"] img', '[data-testid="attachments"]'], 20000)
    if not ok:
        raise RuntimeError("imagem não apareceu no post")
    await asyncio.sleep(ESPERA)

async def descrever_imagem(page, texto):
    botao = await primeiro_visivel(page, [
        'a[href*="/media/"][href*="alt"]', '[data-testid="altTextLabel"]',
        'button:has-text("Adicionar descrição")', 'a:has-text("Adicionar descrição")',
        'button:has-text("Add description")', 'a:has-text("Add description")',
        'button:has-text("ALT")', 'a:has-text("ALT")'])
    if not botao:
        raise RuntimeError("botão 'Adicionar descrição' não encontrado")
    await botao.click()
    campo = await primeiro_visivel(page, ['[data-testid="altTextInput"]', '[role="dialog"] textarea'])
    if not campo:
        raise RuntimeError("campo da descrição não abriu")
    await campo.fill(texto[:1000])
    salvar = await primeiro_visivel(page, ['[data-testid="endEditingButton"]',
                                           '[role="dialog"] button:has-text("Salvar")',
                                           '[role="dialog"] button:has-text("Save")'])
    if not salvar:
        raise RuntimeError("botão 'Salvar' da descrição não encontrado")
    await salvar.click()
    await asyncio.sleep(ESPERA)

async def escrever_texto(page, texto):
    caixa = await primeiro_visivel(page, ['[data-testid="tweetTextarea_0"]', 'div[role="textbox"]'])
    await caixa.click()
    await page.keyboard.insert_text(texto)
    await asyncio.sleep(ESPERA)

MESES = [["janeiro", "january", "jan"], ["fevereiro", "february", "fev", "feb"], ["março", "marco", "march", "mar"],
         ["abril", "april", "abr", "apr"], ["maio", "may", "mai"], ["junho", "june", "jun"],
         ["julho", "july", "jul"], ["agosto", "august", "ago", "aug"], ["setembro", "september", "set", "sep"],
         ["outubro", "october", "out", "oct"], ["novembro", "november", "nov"], ["dezembro", "december", "dez", "dec"]]


async def escolher(select, valores, textos=()):
    """Escolhe uma opção do select pelo valor ou pelo texto visível."""
    opcoes = await select.evaluate("el => [...el.options].map(o => [o.value, o.text.trim().toLowerCase()])")
    for v in valores:
        for valor, _ in opcoes:
            if valor == v:
                await select.select_option(value=valor)
                return
    for t in list(textos) + list(valores):
        for valor, texto in opcoes:
            if texto == t.lower():
                await select.select_option(value=valor)
                return
    raise RuntimeError(f"opção {valores[0]} não existe no campo")


async def definir_horario(page, quando):
    botao = await primeiro_visivel(page, ['[data-testid="scheduleOption"]',
                                          'button[aria-label*="Agendar"]', 'button[aria-label*="Programar"]',
                                          'button[aria-label*="Schedule"]'])
    if not botao:
        raise RuntimeError("ícone de agendamento não encontrado")
    await botao.click()
    await primeiro_visivel(page, ['[role="dialog"] select'], 10000)
    selects = page.locator('[role="dialog"] select')
    total = await selects.count()
    if total < 5:
        raise RuntimeError(f"a tela de agendamento tem {total} campos, eram esperados 5 ou 6")

    # Ordem da tela do X: Mês, Dia, Ano, Hora, Minuto e, em alguns idiomas, AM/PM
    tem_ampm = total >= 6
    h, m = quando.hour, quando.minute
    hora = (h % 12 or 12) if tem_ampm else h
    await escolher(selects.nth(0), [str(quando.month), f"{quando.month:02d}"], MESES[quando.month - 1])
    await escolher(selects.nth(1), [str(quando.day), f"{quando.day:02d}"])
    await escolher(selects.nth(2), [str(quando.year)])
    await escolher(selects.nth(3), [str(hora), f"{hora:02d}"])
    await escolher(selects.nth(4), [str(m), f"{m:02d}"])
    if tem_ampm:
        await escolher(selects.nth(5), ["pm" if h >= 12 else "am", "PM" if h >= 12 else "AM"])
    await asyncio.sleep(ESPERA)

    aviso = page.locator('[role="dialog"]').get_by_text(re.compile(r"(Será enviado|Will send)", re.I)).first
    try:
        print("      X diz:", (await aviso.inner_text()).strip())
    except Exception:
        pass

    confirmar = await primeiro_visivel(page, ['[data-testid="scheduledConfirmationPrimaryAction"]',
                                              '[role="dialog"] button:has-text("Confirmar")',
                                              '[role="dialog"] button:has-text("Confirm")'])
    if not confirmar:
        raise RuntimeError("botão 'Confirmar' não encontrado")
    await confirmar.click()
    await asyncio.sleep(ESPERA)

async def clicar_agendar(page):
    botao = await primeiro_visivel(page, ['[data-testid="tweetButton"]', 'button:has-text("Agendar")'])
    if not botao:
        raise RuntimeError("botão 'Agendar' não encontrado")
    await botao.click()
    await asyncio.sleep(ESPERA * 2)


# ---------- fluxo principal ----------
async def main():
    log = ler_log()
    limite = datetime.now() + timedelta(minutes=10)
    pendentes = [p for p in ler_posts() if p["id"] not in log and p["quando"] > limite]
    if not pendentes:
        print("Nenhum post pendente no posts.csv (os que já passaram do horário são ignorados).")
        return
    print(f"{len(pendentes)} post(s) para agendar:")
    for p in pendentes:
        print(f"  - {p['id']}: {p['texto'][:70]}")
    for p in pendentes:
        if p["imagem"] and not (PASTA / p["imagem"]).exists():
            sys.exit(f"Imagem não encontrada: {p['imagem']}. Confira a pasta cards/.")

    async with async_playwright() as pw:
        abrir_chrome()
        navegador = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORTA}")
        ctx = navegador.contexts[0]
        page = await ctx.new_page()
        await page.goto(f"{BASE}/home")
        if not await primeiro_visivel(page, ['[data-testid="SideNav_NewTweet_Button"]',
                                             '[data-testid="AppTabBar_Home_Link"]'], 8000):
            perguntar("\nFaça login no X na janela que abriu e aperte Enter aqui quando estiver na página inicial: ")

        for p in pendentes:
            print(f"\nPost de {p['id']}")
            passos = [("abrir o compositor", abrir_compositor(page))]
            if p["imagem"]:
                passos.append(("anexar a imagem", anexar_imagem(page, PASTA / p["imagem"])))
                if p["alt"]:
                    passos.append(("colocar a descrição da imagem", descrever_imagem(page, p["alt"])))
            passos += [("escrever o texto", escrever_texto(page, p["texto"])),
                       ("escolher data e hora", definir_horario(page, p["quando"]))]
            continuar = True
            for nome, coro in passos:
                print(f"   {nome}...")
                if not await etapa(nome, coro):
                    continuar = False
                    break
            if not continuar:
                print("   Post pulado.")
                continue

            print(f"   Pronto para agendar: {p['quando']:%d/%m/%Y às %H:%M}")
            if not DIRETO and perguntar("   Confira na janela. Agendar? [s/N]: ") != "s":
                print("   Não agendado.")
                continue
            if await etapa("clicar em Agendar", clicar_agendar(page)):
                log[p["id"]] = {"texto": p["texto"][:60], "agendado_em": datetime.now().isoformat(timespec="minutes")}
                salvar_log(log)
                print("   [ok] Agendado.")

        print("\nTerminado. Confira em Postar > Rascunhos > Agendados.")
        await page.close()
        print("Pode fechar o Chrome quando quiser (o login continua salvo).")

if __name__ == "__main__":
    asyncio.run(main())
