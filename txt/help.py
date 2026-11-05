"""Ajuda atualizada mantendo os comandos da interface original."""

helpMain = """
 [1] Lookup         Consultas públicas, APIs autorizadas e análise local.
 [2] Other tool     Verificação de exposição e gerador local de hash SHA-1.
 [3] Profiler       Consulta, criação, exportação, backup e contas dos perfis.
 [4] Change country Seleciona o país para as pesquisas.
 [5] Tracert         Diagnóstico de rota com filtro de hops e exportação CSV/texto.
 [6] DNS lookup      Consulta de registros DNS e publicação de SPF/DKIM/DMARC.
 [7] Sub-domains     Descoberta passiva combinada; tabela e exportação CSV/JSON.

 [e] Sair    [h] Ajuda    [c] Limpar e redesenhar a tela
"""

helpLookup = """
 [1] Pessoas, [2] username, [3] endereço, [4] telefone,
 [9] empresa/LinkedIn e [10] Google: consulta manual no navegador.
 [5] IP público: geolocalização aproximada por HTTPS.
 [6] BSSID: base pública; não representa rastreamento em tempo real.
 [7] Email: consulta unificada HIBP (exposição), Hunter e Kickbox (entregabilidade).
 CheckLeaked opcional: CHECKLEAKED_API_KEY (Bot Token) e checkleaked_enabled=true.
 Pede confirmação a cada busca; não repete nem pagina automaticamente.
 Proteção local: 2 tentativas/24h e intervalo de 60s, inclusive em caso de falha.
 A cota real depende do serviço e do uso no site. Senhas/hashes não são exibidos.
 Chaves e ativação: configurar-apis.bat abre config.ini na raiz do projeto.
 Sem chave a fonte é informada como não configurada; falhas ficam separadas.
 Accept-all/unknown não confirmam caixa existente. Scores não são reputação do domínio.
 [8] Mail tracer: cabeçalho local; somente IPs públicos são consultados.
 [11] Facebook: me/ID autorizado, exige token e versão Meta Graph.
 [12] Twitter/X: exige X_BEARER_TOKEN e acesso ao endpoint.
 [13] Instagram profissional: exige token/versão Meta e INSTAGRAM_USER_ID.
 [14] EXIF: lê JPEG/TIFF local sem enviar o arquivo.

 Falhas de API são informadas; sem acesso, há consulta manual quando disponível.
 [b] Voltar    [e] Sair    [h] Ajuda    [c] Limpar e redesenhar
"""

helpOtherTool = """
 [1] Verifica exposição de um hash SHA-1 com Pwned Passwords.
 Somente o prefixo de 5 caracteres é transmitido. Não recupera senhas.
 [2] SHA-1 hash generator: gera o hash local de texto/senha em UTF-8.
 Entrada oculta; preserva espaços, maiúsculas e acentos. Funciona offline.
 O texto não é salvo nem enviado. O hash aparece em uma linha para copiar.
 [c] copia somente o hash no Windows; nos demais sistemas, copie manualmente.
 Depois, volte e use [1] para verificar a exposição do hash.
 [b] Voltar    [e] Sair    [h] Ajuda    [c] Limpar e redesenhar
"""

helpProfiler = """
 [1] Profiler          Consulta/atualiza um perfil preservando dados em falhas.
 [2] Show all Profiles Lista os perfis válidos e seus IDs.
 [3] Create profile    Cria um perfil sem substituir outro existente.
 [4] Export profile    Exporta JSON legível na pasta privada de perfis.
 [5] Restore backup    Restaura explicitamente o último backup válido.
 [6] Edit accounts     Atualiza contas; Enter mantém o valor anterior.

 Os perfis ficam fora de www por padrão, com escrita atômica e backup.
 [b] Voltar    [e] Sair    [h] Ajuda    [c] Limpar e redesenhar
"""

helpCountry = """
 [1] França    [2] Bélgica    [3] Suíça    [4] Luxemburgo
 [5] Todos     [6] Brasil
 Também é possível informar diretamente FR, BE, CH, LU, XX ou BR.
 [b] Voltar    [e] Sair    [h] Ajuda    [c] Limpar e redesenhar
"""

helpTracert = """
 [1] Lookup host   Traça a rota até um host ou IP usando o utilitário do sistema.
 Opções: 1–64 hops, timeout total de 1–180 segundos (padrão 30),
 espera por resposta de 100–5000 ms e filtro de hops públicos.
 No macOS, a espera é arredondada para cima para segundos inteiros.
 Hostnames usam IPv4; informe um IPv6 literal para traçar por IPv6.
 O filtro público vale para a tela e para o CSV/texto; não muda as sondagens.
 Arquivos ficam em traces/ dentro da pasta privada configurada de dados.
 Timeout pode produzir resultado parcial. Asteriscos não comprovam falha de rede.
 Logs durante a execução: tempo decorrido, aviso a cada segundo e saltos
 recebidos com IP/RTT/estado. O filtro público também vale para os logs.
 Ctrl+C interrompe o diagnóstico e encerra o processo filho.
 Windows usa tracert; Linux/macOS exigem traceroute/traceroute6 instalado.
 No modo offline, nenhuma sondagem ou resolução de destino é iniciada.
 [b] Voltar    [e] Sair    [h] Ajuda    [c] Limpar e redesenhar
"""

helpDNS = """
 [3] Nameserver / domain registration: NS pelo DNS e dados públicos RDAP
 do registro oficial, selecionado pelo catálogo IANA incluído no projeto.
 Exibe nameservers, datas, status, registrador e titular/contatos publicados.
 Informe o domínio registrado exato, sem URL ou www adicional.
 Dados ocultos não são recuperados. Registrador não é tratado como titular.
 Não exige chave de API; cobertura e quotas dependem do registro.
 O timeout escolhido vale para DNS; RDAP usa os limites HTTPS do cliente.
 [1] Lookup host / record type: A, AAAA, MX, TXT, NS, SOA ou CNAME.
 Exibe registros, TTL e nome canônico quando retornados pelo resolvedor.
 [2] SPF/DKIM/DMARC: consulta TXT no domínio, em _dmarc.domínio e
 em seletor._domainkey.domínio. DKIM exige seletor informado (até 5).
 O seletor aparece como s= e o domínio de assinatura como d= em DKIM-Signature.
 Se não houver seletor, DKIM fica como não verificado, não como ausente.
 Usa o resolvedor configurado no sistema; timeout de 1–15 s por consulta.
 Ausência, NXDOMAIN, timeout e falha de resolvedor são estados distintos.
 A verificação é de publicação direta, não valida assinatura, DNSSEC,
 mecanismos SPF completos nem herança de política DMARC.
 No modo offline, nenhuma consulta DNS é iniciada.
 [b] Voltar    [e] Sair    [h] Ajuda    [c] Limpar e redesenhar
"""

helpSubdomains = """
 [1] Discover domain: consulta crt.sh, CertSpotter e HackerTarget por HTTPS.
 Combina também Subfinder, Amass passivo e Assetfinder quando instalados.
 Subfinder usa todas as fontes disponíveis, conforme chaves e quotas; evita
 repetir as três fontes HTTPS integradas. Amass exige modo passivo compatível.
 [2] Sources / tools status: mostra disponibilidade local, sem consulta de rede.
 Executáveis: .tools/NOME/NOME.exe (Windows) ou NOME no PATH.
 Timeout por executável: 10–300 s; cada resposta HTTPS tem limites próprios.
 Deduplica nomes, restringe ao domínio e mantém a origem de cada resultado.
 Wildcards são evidências separadas; não representam um host confirmado.
 Não resolve DNS nem testa serviços; dados podem ser históricos/incompletos.
 Exporta CSV/JSON completos em subdomains/ na pasta privada configurada.
 Chaves opcionais: CERTSPOTTER_API_KEY e HACKERTARGET_API_KEY.
 SUBFINDER_PROVIDER_CONFIG permite indicar o YAML privado de chaves.
 Consultas consomem quotas e enviam o domínio aos provedores consultados.
 Modo offline não inicia consultas nem executáveis.
 [b] Voltar    [e] Sair    [h] Ajuda    [c] Limpar e redesenhar
"""
