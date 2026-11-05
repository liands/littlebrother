# LittleBrother

Ferramenta de terminal em Python para consultas a fontes públicas (OSINT), análise local de arquivos e organização de perfis. Esta cópia corresponde à revisão local **7.0.0**, derivada do LittleBrother 6.0.2 de Lulz3xploit.

## Funcionalidades

- **Lookup:** pesquisas por pessoa, usuário, endereço, telefone e empresa por links de busca; consultas de IP/BSSID; análise de cabeçalhos de email e metadados EXIF.
- **Email:** integrações opcionais com HIBP, Hunter, Kickbox e CheckLeaked, com estados separados por provedor.
- **Redes sociais:** adaptadores de X, Facebook e Instagram, sujeitos às permissões e planos oficiais.
- **Perfis locais:** criação, listagem, edição, exportação, importação e restauração da última cópia válida.
- **Rede:** tracert/pathtrace, registros DNS, SPF/DKIM/DMARC, nameservers e registro público de domínio por RDAP.
- **Subdomínios:** descoberta passiva via crt.sh, CertSpotter, HackerTarget e executáveis opcionais Subfinder, Amass e Assetfinder; exportação CSV/JSON.
- **SHA-1:** geração local e consulta de exposição via Pwned Passwords por prefixo do hash.
- **Modo offline:** desativa consultas automáticas e abertura de navegador.

Pesquisas por links não confirmam identidades. Resultados passivos não comprovam serviços ativos. Integrações externas dependem de disponibilidade, cobertura, permissões e quotas. Use as consultas apenas em contextos autorizados.

## Instalação e início no Windows

Requisito: Python 3.10 ou superior disponível no PATH; internet para instalar as dependências.

```powershell
git clone https://github.com/liands/littlebrother.git
cd littlebrother
.\instalar.ps1
.\iniciar.bat
```

Se a execução de scripts PowerShell estiver bloqueada, prepare o ambiente manualmente:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\iniciar.bat --check
.\iniciar.bat
```

Nas próximas execuções, abra `iniciar.bat`. Ele usa o ambiente virtual; não instala dependências.

## Como usar

No menu principal, escolha o número da função:

| Opção | Uso |
|---|---|
| 1 — Lookup | Pesquisas e consultas; a opção 7 consulta email |
| 2 — Other tool | Consulta de exposição de hash e geração SHA-1 |
| 3 — Profiler | Gerenciamento dos perfis locais |
| 4 — Change country | Seleção do país das pesquisas; Brasil é a opção 6 |
| 5 — Tracert / Pathtrace | Diagnóstico de rota de um host |
| 6 — DNS lookup | Registros DNS, segurança de email e registro do domínio |
| 7 — Sub-domains | Descoberta passiva e exportação |

Use `h` para ajuda, `c` para redesenhar a tela, `b` para voltar e `e` para sair.

```powershell
.\iniciar.bat --offline
.\iniciar.bat --check
.\iniciar.ps1 --data-dir 'D:\DadosPrivados\LittleBrother'
.\iniciar.ps1 --import-profiles 'D:\BackupPrivado\Watched'
```

## Chaves de API

**Este backup não contém as chaves da instalação original.** `config.ini` é privado e fica fora do Git. O modelo `configuracao.exemplo.ini` tem os campos vazios.

1. Execute `configurar-apis.bat` ou copie `configuracao.exemplo.ini` para `config.ini`.
2. Preencha somente as chaves dos serviços utilizados em `[api_keys]`: `HIBP_API_KEY`, `HUNTER_API_KEY`, `KICKBOX_API_KEY` e, se necessário, `CHECKLEAKED_API_KEY`.
3. Ajuste as opções em `[email_lookup]`. CheckLeaked vem desativado; requer habilitação e confirmação na tela.
4. Inicie a aplicação. Sem chave, a fonte correspondente permanece indisponível.

Variáveis de ambiente prevalecem sobre o INI. X e Meta usam `X_BEARER_TOKEN`, `META_ACCESS_TOKEN`, `META_GRAPH_VERSION` e `INSTAGRAM_USER_ID`, conforme o [guia completo](docs/GUIA_COMPLETO.md). Não publique credenciais. Consultas de email enviam o endereço aos provedores selecionados e podem consumir créditos.

## Linux e macOS

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp configuracao.exemplo.ini config.ini
.venv/bin/python -B LittleBrother.py
```

## Dados e conteúdo do backup

No Windows, perfis ficam por padrão em `%LOCALAPPDATA%\LittleBrother\profiles`; em Linux/macOS, em `$XDG_DATA_HOME/LittleBrother/profiles` ou `~/.local/share/LittleBrother/profiles`. São arquivos locais sem criptografia. Faça o backup privado desses dados separadamente.

Este repositório preserva código, testes, instaladores, Dockerfile e documentação de uso. Exclui configurações privadas, perfis, relatórios locais de consultas/validação, histórico técnico local, caches, ambiente virtual e binários opcionais. Para restaurar a ferramenta, clone o repositório, instale os requisitos e configure suas próprias chaves. O projeto é uma aplicação de terminal; não precisa ser servido pelo Laragon/Apache.

## Verificação

```powershell
.\iniciar.bat --check
New-Item -ItemType Directory -Path .work -Force | Out-Null
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

Os testes simulados não confirmam acesso real a APIs. Instruções de Docker, subdomínios, integrações e limites estão no [guia completo](docs/GUIA_COMPLETO.md).
