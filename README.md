# Agendador de posts no X

Script em Python que agenda vários posts no X (antigo Twitter) de uma vez, a partir de uma planilha.
Para cada post, ele anexa a imagem, preenche a descrição da imagem (texto alternativo), escreve o texto
e escolhe data e hora no **agendador do próprio X**. Antes de agendar, mostra o resumo e pede sua confirmação.

Não usa a API do X: funciona no seu próprio Google Chrome, com o seu login.

> [!WARNING]
> **Leia antes de usar.** As regras de automação do X determinam que a automação seja feita pela API oficial
> e não permitem automatizar o site pelo navegador. Usar este script pode levar à **restrição ou suspensão da sua conta**.
> Ele foi feito para uso pessoal, em baixo volume e com você acompanhando cada post. Use por sua conta e risco
> e consulte as [regras de automação do X](https://help.x.com/rules-and-policies/x-automation).

## Requisitos

- Python 3.9 ou mais recente
- Google Chrome instalado
- Uma conta no X

## Instalação

```bash
git clone https://github.com/bruno-cr/agendador-posts-x.git
cd agendador-posts-x
pip install -r requirements.txt
```

## Como usar

1. Copie `posts_exemplo.csv` para `posts.csv` e preencha com os seus posts.
2. Coloque as imagens na pasta `cards/`.
3. Rode:

```bash
python agendar_x.py
```

4. Na primeira vez, abre uma janela do Chrome separada, só para o X. Faça login nela e aperte Enter no terminal.
   O login fica salvo na pasta `perfil_navegador/` (que **nunca** deve ser compartilhada).
5. Para cada post, o script preenche tudo e pergunta `Agendar? [s/N]`. Confira na janela e digite `s`.

Depois de confiar no resultado, use `python agendar_x.py --direto` para agendar sem confirmar um por um.

## Formato do posts.csv

Separado por **ponto e vírgula** (abre direto no Excel em português), em UTF-8.

| Coluna | Exemplo | Observação |
|---|---|---|
| `data` | `31/10/2026` | dia/mês/ano |
| `hora` | `12:30` | formato 24 horas, no fuso do seu computador |
| `imagem` | `cards/post1.png` | opcional; deixe vazio para post só com texto |
| `texto` | `Minha dica de hoje 👇` | até 280 caracteres |
| `descricao_imagem` | `Card explicando...` | opcional; texto alternativo da imagem, para acessibilidade |

## Como funciona

- Posts com horário que já passou (ou a menos de 10 minutos) são ignorados.
- O arquivo `agendados.json` registra o que já foi agendado, então rodar o script de novo nunca duplica posts.
- O script abre o Chrome comum com uma porta de depuração local (`9222`) e se conecta a ele pelo Playwright.
  Isso evita o bloqueio de login que o X aplica a navegadores abertos por ferramentas de automação.

## Quando algo falha

O X muda o site de vez em quando. Se uma etapa falhar, o script avisa qual foi
(por exemplo, `Não consegui: escolher data e hora`). Você faz aquela etapa na mão, na própria janela,
aperta Enter e ele continua. Ou digite `p` para pular o post.

Se a falha se repetir, abra uma [issue](https://github.com/bruno-cr/agendador-posts-x/issues) com a mensagem do terminal.

Se o X ficar lento, aumente `ESPERA` no topo do `agendar_x.py`.

## Licença

[MIT](LICENSE)
