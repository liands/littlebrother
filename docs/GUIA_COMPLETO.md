# LittleBrother — versão local revisada

Ferramenta de terminal em Python para consultas públicas, análise local e organização de perfis. Esta revisão 7.0.0 parte do LittleBrother 6.0.2 de Lulz3xploit; o projeto original informou que deixou de receber manutenção. 

A interface original foi restaurada: banners ASCII, rosto, painel com data/hora, autor, versão, país e tamanho real da base, cores e prompt `LittleBrother(~)$`. Os menus mantêm `[1] Lookup`, `[2] Other tool`, `[3] Profiler` e `[4] Change country`, com `h` para ajuda, `c` para limpar/redesenhar, `b` para voltar e `e` para sair. O Profiler preserva a numeração original: `[1] Profiler`, `[2] Show all Profiles`, `[3] Create profile`; exportação, restauração e edição ficam nas opções 4–6. Em Change country, Brasil é a opção 6. A ajuda está em português e descreve o funcionamento atualizado de cada integração.

O menu principal também oferece `[5] Tracert / Pathtrace` → `[1] Lookup host`, mantendo a numeração das opções anteriores.

As consultas DNS ficam em `[6] DNS lookup`: `[1] Lookup host / record type`, `[2] SPF / DKIM / DMARC` e `[3] Nameserver / domain registration`.

Em `[7] Sub-domains`, a descoberta passiva combina APIs públicas e ferramentas locais, com origem dos resultados e exportação CSV/JSON.

## Iniciar no Windows

### Primeira execução: instalar os requisitos

É necessário **Python 3.10 ou superior**, disponível pelo comando `python`, e acesso à internet para baixar os pacotes. Os testes desta revisão foram executados no Python 3.13.

**Instale as dependências antes de abrir `iniciar.bat`.** O arquivo `.bat` apenas inicia a aplicação; ele não instala os pacotes de `requirements.txt`.

1. Abra o PowerShell e entre na **raiz do projeto**, onde ficam `LittleBrother.py`, `requirements.txt` e `iniciar.bat` (não na subpasta `MD`):

```powershell
cd littlebrother
python --version
```

2. Execute o instalador e aguarde a mensagem **Instalação concluída**:

```powershell
.\instalar.ps1
```

O instalador cria o ambiente virtual `.venv` quando necessário, prepara o pip, instala os pacotes fixados em `requirements.txt` e executa o diagnóstico `--check`. Se houver erro de instalação, resolva a mensagem apresentada antes de iniciar a aplicação.

3. Abra a aplicação com dois cliques em **`iniciar.bat`**, na raiz do projeto, ou execute no mesmo PowerShell:

```powershell
.\iniciar.bat
```

Nas próximas utilizações, basta abrir `iniciar.bat`. Não é necessário reinstalar os requisitos a cada execução; repita a instalação se recriar o ambiente, trocar de máquina ou atualizar `requirements.txt`. Não é necessário ativar o ambiente virtual nem instalar pacotes no Python global.

### Alternativa: instalar manualmente

Se a política do PowerShell impedir a execução de `instalar.ps1`, execute os comandos abaixo na raiz do projeto. Eles preparam o mesmo ambiente sem alterar a política do sistema:

```powershell
cd littlebrother
python -m venv .venv
.\.venv\Scripts\python.exe -m ensurepip --upgrade
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
.\iniciar.bat --check
.\iniciar.bat
```

Execute cada comando somente depois que o anterior terminar sem erro. Se `python` não for reconhecido, instale/configure o Python no PATH e reabra o PowerShell. Se aparecer `ModuleNotFoundError`, execute novamente a instalação dos requisitos usando o Python de `.venv`, conforme acima.

### Inicialização e configuração opcional

O `iniciar.bat` usa o Python de `.venv`, funciona mesmo quando iniciado de outra pasta e mantém a janela aberta se ocorrer um erro. Também aceita argumentos como `iniciar.bat --offline` (sem consultas de rede) e `iniciar.bat --check` (diagnóstico sem abrir o menu). Como alternativa, use `.\iniciar.ps1` no PowerShell.

Para habilitar integrações de email que exigem chaves, abra `configurar-apis.bat`, preencha o `config.ini` na raiz e siga a seção de configuração abaixo. A falta dessas chaves não impede abrir o programa; somente as fontes correspondentes ficam indisponíveis.

### Linux/macOS

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B LittleBrother.py
```

## Recursos disponíveis e limites

| Recurso | Funcionamento nesta revisão | Configuração |
|---|---|---|
| Perfis locais | Criar, listar, consultar/atualizar, exportar, editar contas e restaurar backup | Nenhuma chave |
| IP público | Consulta HTTPS ao ipwho.is, IPv4/IPv6 e coordenadas aproximadas | Nenhuma chave; disponibilidade do provedor |
| BSSID | Consulta à base pública Wi-Fi de Mylnikov; não é rastreamento em tempo real | Nenhuma chave; cobertura/disponibilidade do provedor |
| Email unificado | Opção Lookup → Email consulta HIBP e CheckLeaked opcional (exposição), Hunter e Kickbox (entregabilidade), com resultados independentes por fonte | config.ini na raiz, chaves de cada serviço e planos/saldos apropriados; CheckLeaked exige seleção explícita |
| Hash SHA-1 | Pwned Passwords: verifica exposição transmitindo somente prefixo de 5 caracteres | Nenhuma chave; não recupera senha nem faz brute force |
| Gerador SHA-1 | Gera localmente o hash de texto/senha em UTF-8, com entrada oculta e opção de copiar o hash no Windows | Funciona offline; biblioteca padrão do Python |
| X / Twitter | Perfil por username pela API v2 | X_BEARER_TOKEN com acesso/plano para endpoint |
| Instagram | Conta profissional autorizada e Business Discovery de perfis elegíveis | Token Meta, versão Graph e INSTAGRAM_USER_ID |
| Facebook | Dados básicos de `me` ou ID autorizado pelo token | Token Meta e versão Graph |
| Pessoas, nome de usuário, endereço, telefone, empresa/LinkedIn e Google | Links de pesquisa parametrizados no navegador; sem coleta automática ou promessa de correspondência | Nenhuma chave; sujeito ao acesso do site |
| Cabeçalhos de email | Analisa campos Received localmente; consulta somente IPs públicos extraídos | Nenhuma chave; arquivo não é enviado |
| EXIF | Lê JPEG/TIFF local, sem enviar imagem | Nenhuma chave |
| Tracert / Pathtrace | Diagnóstico nativo de rota, filtro de hops públicos e exportação CSV/texto | Nenhuma chave; utilitário tracert/traceroute do sistema |
| DNS lookup | Registros A, AAAA, MX, TXT, NS, SOA e CNAME; checagem direta de publicação SPF/DKIM/DMARC | Nenhuma chave; dnspython e resolvedor DNS configurado no sistema |
| Nameserver / domain registration | NS via DNS e nomes de servidores/dados públicos de registro via RDAP oficial: datas, status, registrador e titular/contatos quando publicados | Nenhuma chave; serviço HTTPS selecionado pelo catálogo IANA incluído, sujeito à cobertura e quotas de cada registro |
| Subdomínios | crt.sh, CertSpotter, HackerTarget e Subfinder; adaptadores opcionais Amass/Assetfinder; tabela e CSV/JSON | Chaves opcionais e disponibilidade/quotas das fontes; executáveis opcionais |
| Publicações/timeline de terceiros e SMS público | Indisponíveis nesta revisão; scrapers antigos retirados | Não há substituição automática que contorne controles dos serviços |

A revisão elimina a interpretação de HTML antigo de redes sociais e diretórios. Uma página de login, bloqueio ou erro não é tratada como confirmação de que não existem dados. APIs sociais não oferecem acesso irrestrito a qualquer perfil: dependem das permissões do aplicativo, do token, do tipo de conta e do plano de acesso.

A função interna de fotos do Instagram aceita somente publicações IMAGE da conta profissional autorizada, limitada a 12 itens e aos domínios de mídia permitidos; a interface principal apresenta os dados do perfil. A timeline antiga foi retirada. Brasil foi adicionado às opções de país e pesquisas manuais; isso não transforma os diretórios europeus em bases brasileiras.

## Lookup unificado de email — HIBP, Hunter e Kickbox

A opção existente `[1] Lookup` → `[7] Email lookup` solicita o endereço uma única vez e consulta em paralelo as fontes habilitadas com chave. Não foi criado um menu separado para os validadores. A tela mostra andamento, estado individual por serviço e um resumo de entregabilidade; falha de uma fonte preserva os resultados das outras. Sem chave ou com fonte desativada, essa integração não faz chamadas. O modo offline não inicia essas consultas.

| Fonte | Dados apresentados |
|---|---|
| HIBP v3 | Vazamentos conhecidos, título, domínio e data; ausência de retorno é diferente de falha |
| Hunter Email Verifier v2 | Status detalhado, score de entregabilidade 0–100, sintaxe, MX, SMTP, accept-all, descartável/webmail/bloqueio e data da verificação quando fornecidos |
| Kickbox Verify v2 | Deliverable/undeliverable/risky/unknown, motivo, role (endereço genérico), gratuito/descartável, accept-all, sugestão de correção e Sendex 0–1 |

Campos ausentes aparecem como **não fornecidos**; o programa não inventa um score de reputação do domínio. O score Hunter e o Sendex são escalas próprias do endereço e não são somados ou promediados. Resultados accept-all, unknown ou webmail por si só não confirmam uma caixa individual. Sinais contraditórios entre provedores são destacados. Uma sugestão de correção não é aplicada nem consultada automaticamente. Exposição em vazamentos é mostrada separadamente da entregabilidade; nenhum desses testes garante segurança ou entrega futura. São aceitos endereços comuns com parte local ASCII e domínio internacional convertido para IDNA; endereços com parte local Unicode ou formato entre aspas não fazem parte desta revisão.

### Configurar as chaves com facilidade

1. Na pasta do projeto, abra **`configurar-apis.bat`**. Ele cria `config.ini` na raiz a partir de `configuracao.exemplo.ini` se ainda não existir e abre no Bloco de Notas. Arquivos existentes não são substituídos.
2. Preencha as linhas `HIBP_API_KEY`, `HUNTER_API_KEY` e `KICKBOX_API_KEY` na seção `[api_keys]`, sem aspas. Deixe em branco as fontes que não usar. Salve e feche o editor.
3. Abra `iniciar.bat` e use `[1] Lookup` → `[7] Email lookup`. A configuração é relida a cada consulta; não é necessário reiniciar somente por trocar valores do INI. A atualização de código requer reabrir o programa.

O arquivo padrão em todos os sistemas é **`config.ini` na raiz do projeto**, independentemente da pasta de onde o programa foi iniciado. No Linux/macOS, copie o modelo para esse nome se o arquivo não existir. `LITTLEBROTHER_CONFIG` permite indicar explicitamente outro arquivo e não é alterado por `--data-dir`; variáveis de ambiente continuam tendo prioridade sobre o INI. A configuração anterior de `%LOCALAPPDATA%\LittleBrother\config.ini` foi copiada para a raiz nesta atualização, preservando os valores existentes. O modelo fica sem credenciais e o INI permanece excluído de Git/Docker. O bloqueio web do projeto pelo `.htaccess` foi mantido.

As variáveis de ambiente prevalecem sobre o INI, inclusive se estiverem vazias. Em `[email_lookup]`, `hibp_enabled`, `hunter_enabled` e `kickbox_enabled` aceitam `true`/`false`. `hunter_max_attempts` aceita 1–2 (padrão 2, repetição somente após HTTP 202), e `kickbox_timeout_ms` aceita 1000–10000 ms (padrão 6000). Overrides equivalentes: `HIBP_ENABLED`, `HUNTER_ENABLED`, `KICKBOX_ENABLED`, `HUNTER_MAX_ATTEMPTS`, `KICKBOX_TIMEOUT_MS`. Chaves do arquivo não são exportadas para o ambiente nem repassadas a executáveis de outras ferramentas. `--check` informa apenas se estão configuradas; erros de formato não imprimem linhas do arquivo. Este INI configura as três fontes de email; X/Meta e fontes de subdomínios continuam com as configurações documentadas em suas seções.

Obtenha suas chaves nos serviços oficiais:

- **HIBP:** [assinatura/chave de API](https://haveibeenpwned.com/API/Key); exige acesso autorizado ao endpoint de email.
- **Hunter:** [painel de API keys](https://hunter.io/api-keys); preencha `HUNTER_API_KEY`.
- **Kickbox:** [painel Kickbox](https://app.kickbox.com/), em API Settings → Add API Key; preencha `KICKBOX_API_KEY`.

As consultas enviam o endereço aos provedores habilitados e podem consumir créditos conforme conta/plano. Os serviços realizam suas próprias verificações; o LittleBrother não envia mensagens de email, não usa recursos de disparo/campanha e não grava esses resultados automaticamente em perfis. Retenção e tratamento no provedor dependem do próprio serviço e das configurações da conta.

Hunter usa a chave no header `X-API-KEY`, lê o campo atual `status` e não o `result` obsoleto. A requisição pode levar 20 s e retornar 202; o adaptador permite leitura de 25 s por tentativa, mantendo os limites de tamanho, TLS, redirects e orçamento HTTP. Com duas tentativas, a consulta pode ultrapassar 60 s conforme rede/resolução; o terminal informa as fontes pendentes a cada cinco segundos. Hunter 202 continua pendente após o limite; erros de quota, autenticação, 222, 451 ou timeout não são tratados como email inexistente. Kickbox usa a API v2 e seu parâmetro `apikey`, sem exibir URL com credencial nem o corpo bruto de erros. HTTP 200 com `success=false` é falha, não resultado negativo.

O Hunter foi testado com a credencial pública de demonstração documentada pelo fornecedor. Resultados dessa chave são marcados **DEMONSTRAÇÃO/SANDBOX** e excluídos da conclusão real de entregabilidade. Kickbox também tem chaves Sandbox com respostas fictícias: se usar uma delas, defina `kickbox_sandbox = true` na seção `[email_lookup]` ou `KICKBOX_SANDBOX=true` no ambiente. Chaves com prefixo `test_` são conservadoramente marcadas como demonstração, mas essa identificação não substitui conferir o modo da chave no painel. Use uma chave de produção para verificar endereços reais. Sem chave própria Kickbox, somente o endpoint sem autenticação e os contratos de resposta simulados foram verificados. Não há promessa de saldo, permissões ou verificação real de conta antes de cadastrar suas chaves. Referência: [Sandbox oficial Kickbox](https://docs.kickbox.com/docs/sandbox-api).

Referências: [Hunter API v2](https://hunter.io/api-documentation.md), [Kickbox — SDK oficial e campos da resposta](https://github.com/kickboxio/kickbox-node) e [HIBP API v3](https://haveibeenpwned.com/API/v3).

### CheckLeaked opcional — duas buscas por dia

Integração adicional na mesma opção `[1] Lookup` → `[7] Email lookup`, baseada na documentação oficial consultada em **25/10/2026**. O plano Free anuncia API REST, buscas por email/username, duas buscas por dia e intervalo de 60 s. O token da conta CheckLeaked é obtido em [Bot Links](https://checkleaked.cc/botLinks); use o **Bot Token do CheckLeaked**, não uma chave Hunter/HIBP nem o token de um bot próprio Telegram/Discord. Fonte: [plano Free](https://checkleaked.cc/pricing/free).

Os campos foram acrescentados ao `config.ini` da raiz sem substituir suas chaves existentes. Preencha `CHECKLEAKED_API_KEY` dentro de `[api_keys]` e mude `checkleaked_enabled` para `true` dentro de `[email_lookup]`. Também são aceitos `CHECKLEAKED_API_KEY` e `CHECKLEAKED_ENABLED` no ambiente, com prioridade sobre o arquivo. A integração fica desativada por padrão. Ao consultar um email com a fonte ativada e configurada, a tela pergunta se deseja usá-la naquela consulta; Enter ou `n` preserva a cota. A função interna também exige `consult_checkleaked=True` explicitamente. Os outros provedores seguem seus próprios controles.

O adaptador realiza **uma única requisição** `GET https://api.checkleaked.cc/api/leak_check`, com `check=<email>` e `type=email`, autenticando em `api-key`. Não usa tipo automático, chave LeakCheck customizada, buscas por domínio/senha, paginação, desbloqueio, bots, tracking, campanhas, endpoints de hash cracking ou repetição automática. O host foi adicionado ao cliente HTTPS existente, mantendo TLS, limites de resposta/tempo e bloqueio de redirects. HTTP 401, 429, timeout e JSON com falha não viram confirmação de ausência. Referências: [documentação de desenvolvimento](https://checkleaked.cc/developers), [OpenAPI oficial](https://api.checkleaked.cc/docs/openapi.json).

A resposta é filtrada para contagem informada, metadados das fontes (nome/data) e tipos de campos encontrados. Senhas, hashes e valores de credenciais não são exibidos, exportados ou gravados pelo adaptador. O email de cada registro, quando informado, precisa corresponder ao endereço consultado. A análise limita-se aos primeiros 1.000 registros recebidos e informa resultado parcial quando o total indicado for maior; não faz buscas adicionais. As fontes podem sobrepor dados já retornados pelo HIBP, por isso as contagens ficam separadas e não representam um total global de vazamentos únicos. Nenhum desses achados determina entregabilidade.

Há uma proteção local conservadora: **até duas tentativas em uma janela móvel de 24 horas por chave** e **60 segundos entre elas**, inclusive entre instâncias do programa. Tentativas são reservadas atomicamente antes da chamada e continuam contabilizadas quando há timeout, falha ou resposta inesperada, pois não é possível garantir se o serviço consumiu crédito. O arquivo `checkleaked_usage.sqlite3`, na pasta configurada de dados/perfis, contém somente timestamps e uma identificação SHA-256 da chave; não guarda a chave original, emails nem resultados. Falha no controle de cota impede a chamada. Arquivos desse controle ficam fora de Git/Docker.

O contador **não conhece o saldo real** nem o uso no site, em bots ou em outras máquinas. A janela móvel local pode ser mais restritiva que a virada diária do serviço; a API e o plano da sua conta continuam sendo a autoridade sobre o saldo disponível. O programa não consulta `/valid` ou outros endpoints automaticamente para testar a chave. `--check` também não consome busca. Durante a implementação, foram lidas apenas páginas e especificações públicas; **nenhuma busca autenticada ou consulta de email CheckLeaked foi executada**. A integração foi validada por testes simulados do contrato documentado, aguardando sua chave para uso real.

Na revisão do retorno de erro em 25/10/2026, o token configurado foi validado manualmente com `GET /api/valid`, endpoint que a documentação declara não executar busca: retornou sucesso e plano Free. Não foi repetida a busca por email, e não se conhece o corpo da resposta da tentativa anterior. Foi corrigida uma divergência entre o OpenAPI e o SDK oficial: o leitor aceita tanto `result`/`source.name`/`source.date` com `success=true` quanto `results`/`sources`/`lastBreach` com metadados `Name`, `Leak`, `BreachDate` e `success` ausente ou nulo, desde que `found` e a lista sejam válidos. Um `success=false` explícito ou campo `error` continua sendo falha; payload incompleto não vira ausência. Erros reconhecidos no corpo de uma resposta HTTP 200 são classificados como autenticação, quota, cooldown, parâmetros ou serviço indisponível, sem mostrar texto bruto, token ou credenciais. Mensagens não reconhecidas ficam explicitamente inconclusivas. O adaptador continua fazendo uma única busca e não altera o contador para repetir tentativas. Referência complementar: [tipos do SDK oficial](https://github.com/eduair94/CheckLeakedCC/blob/main/src/types.ts).

A exibição do CheckLeaked tem resumo com contagem informada, fontes/datas listadas e linhas analisadas, seguido de tabela numerada em ordem alfabética e lista dos tipos de dados expostos. Datas ISO são apresentadas como `DD/MM/AAAA`; `N/D` indica data não informada, e valores de data não reconhecidos são mantidos. Nomes e URLs longos quebram em linhas sem truncar o conteúdo. A tabela se ajusta à largura do terminal (até 110 colunas); abaixo de 64 colunas, usa uma lista por fonte para preservar a leitura. Uma linha pode mencionar várias fontes e a mesma fonte pode aparecer em datas diferentes, portanto as contagens não são somadas como vazamentos únicos. Essa formatação é local e não faz chamadas adicionais.

## Gerar SHA-1 para consultar exposição

Abra `[2] Other tool` → `[2] SHA-1 hash generator`, logo abaixo de `[1] SHA-1 exposure check`. Digite ou cole o texto/senha na entrada oculta e pressione Enter. A ferramenta calcula o SHA-1 localmente, mostra os 40 caracteres hexadecimais em uma linha e permite `[c] Copiar hash` no Windows. A cópia usa o `clip.exe` do diretório System32, recebe somente o hash e substitui o conteúdo atual da área de transferência quando você escolhe copiar. Nos demais sistemas, ou em falha da cópia automática, selecione e copie a linha manualmente.

Pressione Enter para voltar, escolha `[1] SHA-1 exposure check` e cole o hash. A geração funciona offline e não envia nem grava o texto/senha; a consulta de exposição continua sendo uma ação separada e envia apenas o prefixo de cinco caracteres. O texto é codificado em UTF-8 exatamente como informado: espaços, maiúsculas e acentos não são removidos ou normalizados. Uma entrada vazia gera o hash do texto vazio. Se o terminal não permitir entrada oculta, a operação é recusada em vez de exibir a senha durante a digitação; abra pelo `iniciar.bat` em um terminal interativo.

## Tracert / Pathtrace

Abra `[5] Tracert / Pathtrace` no menu principal e selecione `[1] Lookup host`. Informe um domínio (como `example.com`) ou um IP. URLs, portas, caminhos e opções de linha de comando são recusados. O destino pode ser local ou público; endereços multicast, não especificados e broadcast são recusados.

Opções disponíveis:

- **Máximo de hops:** 1–64; padrão 30.
- **Timeout do processo:** 1–180 segundos; padrão 30. Ao atingir o limite, o processo é encerrado e os saltos capturados são apresentados como resultado parcial.
- **Espera por resposta:** 100–5000 ms; padrão 1000 ms. No macOS, esse valor é arredondado para cima para segundos inteiros e o valor efetivo aparece no relatório.
- **Somente hops públicos:** filtra os IPs privados/reservados e os saltos sem IP na tela e nas exportações. Não altera as sondagens e não anonimiza o destino informado. Os números originais dos saltos são preservados. Os RTTs são agrupados por salto, que pode ter respostas de mais de um IP.

O programa usa `tracert.exe` no Windows, `traceroute` no Linux e `traceroute`/`traceroute6` no macOS, sem executar um shell. Hostnames usam IPv4; um IPv6 literal seleciona IPv6. Não há consulta a uma API externa para traçar a rota. O diagnóstico envia sondagens pela rede até o destino e pode fazer a resolução DNS do hostname.

Durante a execução, o terminal exibe logs com tempo decorrido, um aviso de andamento a cada segundo e cada salto assim que sua linha é recebida do utilitário (IP, RTTs e estado). O filtro de hops públicos também vale para esses logs. Se o utilitário demorar ou acumular a saída antes de enviá-la, o aviso de andamento continua aparecendo; ele não representa um percentual estimado de conclusão. Timeout informa resultado parcial e Ctrl+C encerra o processo filho antes de sair. Ao terminar, o resumo e as exportações continuam disponíveis.

Windows normalmente já fornece o utilitário. No Linux/macOS, ele deve estar instalado, disponível no PATH e ter as permissões exigidas pelo sistema. A ferramenta informa a ausência ou falha sem instalar pacotes ou elevar permissões automaticamente. No modo `--offline`, não inicia o utilitário nem resolve o destino.

Ao terminar, escolha `[1] CSV`, `[2] Texto` ou Enter para voltar. É possível exportar os dois formatos. Os arquivos recebem nomes únicos e ficam em `traces/` dentro da pasta privada de dados: por padrão, `%LOCALAPPDATA%\LittleBrother\profiles\traces` no Windows. O CSV usa UTF-8 com BOM para facilitar a abertura no Excel; inclui opções, estado do processo e saltos visíveis. Os arquivos não são enviados a terceiros.

Asteriscos indicam ausência de resposta à sondagem, que pode resultar de filtragem ou de roteadores que não respondem. O encerramento do comando não comprova que o destino foi alcançado: o relatório informa separadamente se o IP do destino apareceu nos saltos.

Referências dos comandos: [Microsoft tracert](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/tracert), [manual traceroute Linux](https://man7.org/linux/man-pages/man8/traceroute.8.html) e [manual Apple traceroute6](https://github.com/apple-oss-distributions/network_cmds/blob/main/traceroute6.tproj/traceroute6.8).

## Consulta de DNS e registros de email

Em `[6] DNS lookup` → `[1] Lookup host / record type`, informe o nome DNS e escolha `A`, `AAAA`, `MX`, `TXT`, `NS`, `SOA` ou `CNAME`. O tipo padrão é `A`. A resposta mostra registros, TTL em segundos e nome canônico quando disponíveis. Registros TXT divididos em fragmentos dentro do mesmo registro são reunidos corretamente. Para TXT de serviços, nomes como `_dmarc.example.com` e `s1._domainkey.example.com` são aceitos.

A consulta usa o resolvedor configurado no Windows/Linux/macOS, com nome absoluto e sem acrescentar sufixos de pesquisa locais. O timeout é de 1–15 segundos **por consulta**, padrão 5. `NXDOMAIN`, ausência do tipo solicitado, timeout e falha do resolvedor têm estados distintos. Sem resposta por timeout não é interpretado como ausência de registro. URLs, IPs literais, portas, caminhos e tipos fora da lista são recusados; consulta reversa/PTR não foi incluída.

Em `[2] SPF / DKIM / DMARC`, informe o domínio e, opcionalmente, até cinco seletores DKIM separados por vírgula:

- **SPF:** procura `v=spf1` nos registros TXT do domínio exato; sinaliza múltiplos registros correspondentes. Não avalia toda a cadeia de `include`/`redirect`, remetente/IP autorizado ou limites de consultas SPF.
- **DMARC:** consulta TXT em `_dmarc.<domínio>`, apresenta a política `p=`, diferencia monitoramento (`p=none`) e sinaliza tags repetidas/política inválida. Não calcula herança do domínio organizacional nem a política efetiva de entrega.
- **DKIM:** consulta TXT em `<seletor>._domainkey.<domínio>`. O seletor pode ser obtido em `s=` e o domínio de assinatura em `d=` no cabeçalho `DKIM-Signature`. Não há tentativa automática de adivinhar seletores. Sem seletor, aparece **não verificado**, em vez de ausente. Chave com `p=` vazio é sinalizada como revogada. A estrutura criptográfica e a assinatura de uma mensagem não são validadas.

As verificações se referem aos nomes exatos consultados. Se o domínio `d=` da assinatura DKIM for diferente do domínio analisado, consulte esse domínio com o seletor correspondente. Podem ocorrer até sete consultas na checagem (SPF, DMARC e cinco seletores), cada uma sujeita ao timeout escolhido.

DNS é um diagnóstico separado das APIs HTTP: usa o transporte do resolvedor DNS, normalmente UDP/TCP na porta 53, e não garante criptografia nem validação DNSSEC. O modo `--offline` impede consultas DNS. Nenhuma chave de API adicional é necessária. O pacote `dnspython==2.9.0` está fixado no requirements.txt e já foi instalado no ambiente virtual desta máquina; para outra instalação, execute instalar.ps1.

Referências: [dnspython Resolver](https://dnspython.readthedocs.io/en/stable/resolver-class.html), [SPF — RFC 7208](https://www.rfc-editor.org/rfc/rfc7208), [DKIM — RFC 6376](https://www.rfc-editor.org/rfc/rfc6376) e [DMARC — RFC 7489](https://www.rfc-editor.org/rfc/rfc7489).

## Consulta de nameservers e registro público

Em `[6] DNS lookup` → `[3] Nameserver / domain registration`, informe o domínio registrado exato, por exemplo `empresa.com.br` ou `example.com`, sem URL, porta ou `www` adicional. A opção reúne duas consultas independentes e mostra suas etapas:

- **DNS NS:** nameservers retornados pelo resolvedor configurado no sistema, TTL e estado da consulta. Usa o timeout DNS escolhido (1–15 segundos; padrão 5), com as mesmas distinções entre ausência, NXDOMAIN, timeout e erro do menu DNS.
- **RDAP oficial:** endpoint do registro selecionado por correspondência de sufixo mais longo no catálogo oficial IANA incluído em `lib/rdap-bootstrap.json`. Para `.br`, usa `https://rdap.registro.br/domain/<domínio>`; `.com` usa Verisign e `.org` usa Public Interest Registry. Não exige chave de API nesta integração. O catálogo obtido em 23/10/2026 tem publicação IANA de `2026-10-22T23:00:04Z`; são 592 entradas de serviços para 1.204 sufixos, incluindo alguns que só anunciam HTTP e são recusados pela ferramenta.

O RDAP apresenta, quando retornados: nameservers cadastrados, identificador do domínio, status de registro, datas de criação/alteração/expiração e informação de delegação assinada (`secureDNS.delegationSigned`). Nas entidades, mostra nome/organização, endereço, email, telefone e identificadores públicos publicados. Titular (`registrant`), registrador (`registrar`), contatos técnicos, administrativos e de abuso são identificados por seus papéis. Um registrador não é apresentado como se fosse o titular. A indicação de DNSSEC é a declaração do registro, sem validação criptográfica da cadeia.

Dados pessoais podem estar ocultos, incompletos ou representar um serviço de privacidade. Sem entidade do titular com campos públicos, a ferramenta informa **dados não fornecidos nesta resposta**, mesmo quando há informações do registrador. Campos marcados como ocultados e avisos do provedor também são sinalizados. Não há tentativa de recuperar informações restritas ou inferir a identidade a partir dos nameservers. Alguns registros só fornecem detalhes adicionais em outro serviço do registrador; o adaptador atual não segue essas referências.

Quando ambas as listas de nameservers são fornecidas, a ferramenta compara os nomes. Uma diferença pode decorrer de caches, delegação ou atualização; a consulta NS pelo resolvedor não é uma inspeção direta da delegação na zona pai. Falha de DNS não impede mostrar RDAP, e falha de RDAP não apaga o resultado DNS. HTTP 404 não é tratado como confirmação de disponibilidade para compra: confira se informou o domínio registrado, pois o adaptador consulta o nome exato e não remove subdomínios automaticamente. Há estados específicos para quota/429 e extensão sem serviço compatível.

O RDAP mantém HTTPS validado, teto de 2 MiB por resposta, limites de tempo do cliente HTTP, ausência de credenciais/proxies herdados e redirecionamentos bloqueados. O timeout escolhido na tela vale para DNS; não substitui os timeouts HTTP (conexão 5 s, leitura 12 s e orçamento de leitura de 30 s, sujeito às limitações descritas na seção de rede). A permissão RDAP é separada da allowlist das demais APIs: aceita apenas a URL de consulta de domínio selecionada do catálogo IANA, sem URLs arbitrárias, parâmetros extras, consultas a entidades ou links externos presentes na resposta. O catálogo é empacotado, sem atualização automática durante as consultas; alterações futuras de serviços exigem revisar/atualizar esse arquivo e reiniciar o programa.

As respostas são exibidas no terminal; esta opção não grava contatos automaticamente em perfis ou relatórios. O modo `--offline` não inicia DNS nem RDAP. Não há dependência Python nova.

Referências oficiais: [catálogo RDAP da IANA](https://data.iana.org/rdap/dns.json), [descoberta de serviço — RFC 9224](https://www.rfc-editor.org/rfc/rfc9224.html), [respostas RDAP — RFC 9083](https://www.rfc-editor.org/rfc/rfc9083.html) e [Registro.br — RDAP](https://registro.br/rdap/).

## Rastreamento de subdomínios

Abra `[7] Sub-domains` → `[1] Discover domain`, informe somente o domínio e escolha o timeout dos executáveis (10–300 s; padrão 90). A opção `[2] Sources / tools status` inspeciona a disponibilidade local sem consultar a rede. A interface ASCII e os comandos `h/c/b/e` permanecem disponíveis.

As fontes são consultadas em paralelo e os nomes são normalizados (IDNA, caixa e ponto final), deduplicados e restritos ao domínio informado. O domínio raiz não entra como subdomínio. Cada nome mantém suas fontes de origem:

| Fonte | Integração atual |
|---|---|
| crt.sh | Consulta HTTPS de nomes em certificados públicos; inclui dados históricos |
| CertSpotter | API HTTPS de emissões não expiradas, com paginação; chave opcional `CERTSPOTTER_API_KEY` |
| HackerTarget | API HTTPS Host Search; chave opcional `HACKERTARGET_API_KEY` |
| Subfinder | **2.17.0 instalado localmente nesta máquina**, distribuição oficial e SHA-256 verificado; todas as fontes passivas disponíveis, conforme credenciais e quotas |
| Amass | Adaptador opcional; só executa versões cujo `enum -h` anuncie `-passive`. Versões incompatíveis são informadas e ignoradas |
| Assetfinder | Adaptador opcional com `--subs-only`; exige executável instalado |

Amass e Assetfinder **não estão instalados nesta máquina**. Para detectá-los, coloque o executável oficial no PATH ou em `.tools/NOME/NOME.exe` (Windows); Linux/macOS usam o nome sem `.exe`. O Subfinder espera os parâmetros da versão 2.17.0. Para repetir sua instalação local em outro Windows x64:

```powershell
.\instalar-subfinder.ps1
```

O instalador fixa a versão 2.17.0 e verifica o SHA-256 `a3fd612928d591fb31c1e59a2e06055e364421ba32251e553073f5673a2d3103` do ZIP oficial antes de extraí-lo. Não altera o PATH. A licença MIT é preservada em `.tools/subfinder/LICENSE.md`; a pasta de binários está excluída do Git e da imagem Docker. A instalação padrão de dependências Python não baixa esses binários opcionais.

O Subfinder é chamado com `-all`, `-oJ`, `-cs`, `-duc`, sem ativar resolução DNS, usando configuração de flags vazia e argumentos explícitos. Exclui `crtsh,certspotter,hackertarget` da coleta interna para evitar repetir as três consultas diretas. Origens detalhadas que ele informar são registradas como `subfinder:fonte`. Para fontes que exigem credenciais, utiliza `SUBFINDER_PROVIDER_CONFIG` apontando para um YAML privado ou o arquivo padrão do usuário (`%APPDATA%\subfinder\provider-config.yaml` no Windows; `~/.config/subfinder/provider-config.yaml` nos demais sistemas). Sem arquivo, utiliza configuração temporária vazia. Chaves não são copiadas para os relatórios. Credenciais específicas de outros executáveis continuam sob responsabilidade de suas configurações oficiais.

Limites e interpretação dos resultados:

- Até 20.000 nomes/padrões por fonte, respostas HTTPS diretas de até 2 MiB e até cinco páginas do CertSpotter. O Subfinder também limita respostas a 2 MiB e resultados de fontes paginadas a 20.000, com limite global de cinco requisições por segundo. Cada executável tem seu timeout e saída capturada em arquivo, com teto de 10 MiB por fluxo verificado durante a execução; ao atingir limite/timeout, é encerrado e os nomes já capturados são preservados.
- O prazo interno do Subfinder é em minutos; com o padrão de 90 s, usa um minuto de coleta e reserva margem para finalizar. Prazos externos menores que um minuto podem interromper o utilitário antes de ele publicar resultados. O limite de executáveis não é um timeout global da consulta: cada resposta HTTP tem os limites do cliente central, e as páginas do CertSpotter são sequenciais.
- O HackerTarget gratuito pode limitar uma resposta a 50 registros; ao alcançar esse número o relatório sinaliza possível corte. O CertSpotter limita consultas sem autenticação e solicita conta/chave para produção. Planos e quotas dos provedores podem mudar.
- `ok` significa que a chamada/adaptador concluiu; não significa cobertura completa do domínio ou sucesso de todos os provedores internos de um executável. Há estados distintos para erro, resultado parcial, ferramenta ausente, versão incompatível e offline. Falha ou quota não vira confirmação de ausência.
- Evidência passiva **não comprova DNS atual, serviço ativo ou propriedade**. Não são feitas requisições aos hosts descobertos nem consultas DNS de validação. Certificados wildcard (`*.example.com`) ficam separados em `wildcards`; o programa não inventa hosts concretos a partir deles. Para uma consulta DNS pontual, use o menu `[6]`.

A tela mostra até 200 nomes e o resumo de todas as fontes. Ao terminar, escolha `j` (JSON), `c` (CSV) ou `a` (ambos). Os arquivos incluem **todos os nomes obtidos**, origens, padrões wildcard, data UTC, limites e estados das fontes, inclusive falhas. São gravados com nomes únicos em `subdomains/` dentro da pasta privada configurada. CSV usa UTF-8 com BOM e linhas `report`, `host`, `wildcard` e `source`, permitindo filtrar no Excel sem perder o contexto da coleta.

As APIs diretas passam pelo cliente HTTPS central. Os executáveis externos usam seus próprios clientes e provedores; não herdam a allowlist de rede do Python. A consulta envia o domínio a terceiros e consome quotas. No modo `--offline`, o LittleBrother não inicia essas chamadas nem executáveis. Nenhuma credencial foi cadastrada automaticamente.

Referências oficiais: [Subfinder — parâmetros](https://docs.projectdiscovery.io/opensource/subfinder/usage), [lançamento 2.17.0](https://github.com/projectdiscovery/subfinder/releases/tag/v2.17.0), [CertSpotter — API e autenticação](https://sslmate.com/help/reference/ct_search_api_v1), [HackerTarget — Host Search](https://hackertarget.com/find-dns-host-records/), [Amass](https://github.com/owasp-amass/amass) e [Assetfinder](https://github.com/tomnomnom/assetfinder).

## Configurar integrações opcionais

Defina as variáveis no mesmo PowerShell antes de iniciar. Os valores abaixo são exemplos, não credenciais válidas:

```powershell
$env:HIBP_API_KEY = 'SUA_CHAVE_HEXADECIMAL_DE_32_CARACTERES'
$env:X_BEARER_TOKEN = 'SEU_TOKEN_X'
$env:META_ACCESS_TOKEN = 'SEU_TOKEN_META'
$env:META_GRAPH_VERSION = 'v26.0'
$env:INSTAGRAM_USER_ID = 'ID_NUMERICO_DA_CONTA_PROFISSIONAL'
# Opcional para Facebook quando o adaptador recebe perfil vazio:
$env:FACEBOOK_USER_ID = 'me'
.\iniciar.ps1
```

Use a versão Graph suportada pelo aplicativo Meta. A versão não é escolhida automaticamente: o exemplo v26.0 foi conferido no SDK oficial. O adaptador Instagram implementa Facebook Login/Instagram Graph para conta profissional; tokens do fluxo Instagram Login são diferentes e não são intercambiáveis aqui. As permissões e aprovação necessárias devem ser conferidas no painel e na documentação oficial do aplicativo. Não coloque tokens no código, em perfis, argumentos de linha de comando ou arquivos servidos pela web. O programa não carrega `.env` automaticamente e `--check` mostra apenas se cada variável foi definida, sem exibir seu valor.

Fontes oficiais usadas:

- [HIBP API v3 e Pwned Passwords](https://haveibeenpwned.com/API/v3)
- [X API — perfil por username](https://docs.x.com/x-api/users/get-user-by-username)
- [SDK oficial Meta: versão Graph](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/apiconfig.py)
- [SDK oficial Meta: IGUser e Business Discovery](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/iguser.py)
- [Documentação ipwho.is](https://ipwhois.io/documentation)
- [Documentação Mylnikov Wi-Fi](https://www.mylnikov.org/archives/1170)

## Perfis, backup e migração

No Windows, o destino padrão é `%LOCALAPPDATA%\LittleBrother\profiles`, fora de `C:\laragon\www`. No Linux/macOS, é `$XDG_DATA_HOME/LittleBrother/profiles`, ou `~/.local/share/LittleBrother/profiles`. Alteração explícita:

```powershell
.\iniciar.ps1 --data-dir 'D:\DadosPrivados\LittleBrother'
```

Escolha uma pasta privada, fora do document root. A proteção do diretório no Windows também depende das permissões da sua conta e do disco. Os arquivos são JSON/texto locais; não são criptografados.

A gravação usa arquivo temporário, sincronização e substituição atômica. Atualizações mantêm `.prfl.bak` com a última versão válida. Falhas de consulta não apagam os dados anteriores. O menu oferece restauração explícita do backup, que é validado antes da troca. Não apague os arquivos `.lock` enquanto houver instâncias em execução; eles são usados no controle de concorrência e podem permanecer na pasta.

Para importar uma pasta Watched antiga sem apagar a origem:

```powershell
.\iniciar.ps1 --import-profiles 'C:\caminho\Watched'
```

Perfis inválidos são informados e ignorados. Destinos já existentes não são substituídos. Nomes com espaços são normalizados com sublinhados no destino; colisões são recusadas. A importação é explícita e não acontece ao iniciar.

## Rede e proteção do diretório

A inicialização não consulta a internet. As chamadas HTTP às APIs usam HTTPS validado, allowlist de domínios, limites de tamanho, timeout de conexão/leitura e bloqueio de redirecionamentos. O cliente HTTP não herda proxies ou credenciais `.netrc`. Transferências excessivas e respostas inválidas produzem erro explícito. O orçamento de leitura é conferido entre leituras; uma resolução DNS ou leitura em andamento pode levar mais tempo que o orçamento antes de retornar ao programa. Tracert e DNS usam os mecanismos de rede descritos nas respectivas seções, separadamente do cliente HTTP.

Para trabalhar com perfis sem consultas nem abertura de navegador:

```powershell
.\iniciar.ps1 --offline
```

Há `.htaccess` com `Require all denied` porque este projeto é uma aplicação de terminal. A regra depende do Apache permitir `.htaccess`. Em Nginx, bloqueie o diretório na configuração do servidor ou mova o código para fora de www. A existência do arquivo não comprova por si só a configuração de qualquer servidor.

## Verificação

```powershell
.\iniciar.ps1 --check
.\.venv\Scripts\python.exe -m pip check
```

O diagnóstico `--check` informa dependências e configuração sem realizar consultas externas. `pip check` verifica a compatibilidade das dependências instaladas.
