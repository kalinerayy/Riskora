# Riskora (V1)

Plataforma de GRC (governança, riscos e conformidade) para ativos tecnológicos: cadastro de ativos, avaliação de
controles por questionários específicos, identificação de fragilidades potenciais, análise de riscos, recomendação de
controles, plano de tratamento e relatórios. A versão 1 traz o módulo completo de **Backup e Recuperação de Dados**; as
demais categorias de ativos podem ser cadastradas, mas a avaliação delas ainda não está implementada.

Arquitetura, modelo de dados e metodologia: [`docs/arquitetura.md`](docs/arquitetura.md).

## Instalação e execução

Requer Python 3.10 ou superior.

**Linux / macOS**
```bash
cd riskora
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.create_admin --email voce@exemplo.com --name "Seu Nome" --org-name "Minha Organização" --org-slug minha-org
streamlit run app.py
```

**Windows (PowerShell)**
```powershell
cd riskora
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m scripts.create_admin --email voce@exemplo.com --name "Seu Nome" --org-name "Minha Organização" --org-slug minha-org
streamlit run app.py
```
Se o PowerShell bloquear a ativação: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.

O script `create_admin` pede a senha no terminal (mínimo de 10 caracteres). Nenhuma credencial fica no código.
O banco é criado em `data/riskora.db` (ou no caminho da variável `RISKORA_DB`) e as migrações são aplicadas sozinhas.

### Demonstração (dados fictícios)
```bash
python -m scripts.load_demo --email voce@exemplo.com
```
Cria uma organização separada (`demo-riskora`, marcada como demonstração) com 5 ativos de backup avaliados e 1 ativo de
outra categoria, e concede acesso ao usuário informado. Escolha-a no seletor de organização. Ela não se mistura com os
dados reais e não cria usuários nem senhas.

### Acesso de visitante (entrar sem cadastro)
Vem **ligado por padrão**: a tela de login mostra o botão **"Entrar como visitante"**. Qualquer pessoa entra sem conta,
**somente na organização de demonstração** (dados fictícios), com o perfil **Visitante**. Nada a configurar.

O que o visitante **pode**: cadastrar e editar ativos, iniciar e concluir avaliações, registrar e validar ações de
tratamento, reavaliar riscos e exportar relatórios.

O que o visitante **não pode**: gerenciar usuários, editar a organização, ver a auditoria, nem acessar qualquer outra
organização. **Privacidade:** ele nunca vê nome nem e-mail de pessoas que fazem login; onde apareceria um nome (avaliador,
histórico de ações, relatórios), vê "Usuário da organização". O que visitantes fizeram aparece como "Visitante".

A demonstração é **compartilhada**: o que um visitante altera, os outros veem. Para voltar ao estado original:
```bash
python -m scripts.reset_demo --yes
```
Isso arquiva a demonstração atual (nada é apagado) e cria uma nova, devolvendo o acesso a quem já o tinha.

Para **desligar** o visitante (por exemplo, em servidor público com dados reais), antes de rodar o app:
```powershell
$env:RISKORA_GUEST_ACCESS = "off"     # Windows (PowerShell)
streamlit run app.py
```
```bash
RISKORA_GUEST_ACCESS=off streamlit run app.py     # Linux / macOS
```
As variáveis de ambiente são lidas quando o app **inicia**: depois de mudá-las, pare o app (`Ctrl+C`) e rode de novo.

- `RISKORA_GUEST_ROLE` define o perfil do visitante: `guest` (padrão), `reader` (somente leitura), `analyst` ou `manager`.
  Perfil de administrador nunca é aceito. O perfil `guest` não pode ser atribuído a usuários reais.
- O visitante é um usuário com senha aleatória que ninguém conhece (não dá para entrar com senha) e nunca pertence a
  organizações reais. Cada entrada é registrada na auditoria (`guest_login`).
- A organização de demonstração é criada automaticamente na primeira entrada de um visitante.
- Em hospedagem pública, qualquer pessoa na internet poderá abrir e editar a demonstração. Use HTTPS (proxy) e
  restaure a demonstração de tempos em tempos.

### Outros comandos
```bash
pytest                          # testes automatizados
python -m scripts.backup_db     # cópia de segurança do banco em backups/
python -m scripts.reset_demo --yes   # restaura a demonstração compartilhada
```

## Perfis e permissões
| Ação | Administrador | Gestor | Analista | Leitor |
|---|---|---|---|---|
| Gerenciar usuários, organização, auditoria | Sim | Não | Não | Não |
| Cadastrar e editar ativos | Sim | Não | Sim | Não |
| Iniciar, responder e concluir avaliações | Sim | Não | Sim | Não |
| Registrar ações de tratamento e evidências | Sim | Não | Sim | Não |
| Validar ações e registrar risco residual | Sim | Sim | Não | Não |
| Consultar tudo e exportar relatórios | Sim | Sim | Sim | Sim |

O perfil **Visitante** (só no acesso de visitante, na demonstração) tem todas as permissões acima, exceto gerenciar
usuários, organização e auditoria.

As permissões são verificadas nos serviços (backend), e a interface apenas esconde o que o perfil não pode usar.

## Segurança: o que existe e o que não existe
**Implementado e testado:** senhas com hash scrypt; sessões no servidor (só o hash do token é guardado) com expiração por
inatividade e por tempo absoluto; bloqueio temporário após falhas seguidas e mensagem de login única; recuperação de
senha por token de uso único emitido pelo administrador; autorização por perfil nos serviços; isolamento entre
organizações (serviços e chaves estrangeiras compostas); SQL parametrizado; validação de entradas; auditoria sem dados
sensíveis; avaliações concluídas imutáveis (também por gatilhos no banco); CSV protegido contra injeção de fórmulas;
nenhuma telemetria (`gatherUsageStats = false`), nenhum envio externo, nenhuma varredura de rede.

**Limitações conhecidas:**
- O Streamlit serve HTTP por padrão. Fora do seu computador, use um proxy com HTTPS.
- Banco SQLite sem criptografia em repouso e com um escritor por vez (equipes pequenas).
- Sem autenticação multifator e sem envio de e-mail.
- Recarregar a página encerra a sessão (não há cookie persistente).
- O acesso de visitante (ligado por padrão) compartilha uma única organização de demonstração entre todos os visitantes.
- Sem upload de evidências: apenas referências textuais.
- Sem exportação em PDF (CSV e Markdown disponíveis).
- Sem revisão de segurança independente. Documente e revise antes de qualquer uso corporativo em produção.

## Referências a frameworks
Todas as referências do catálogo (CIS v8.1, NIST CSF 2.0, ISO/IEC 27002) estão como **"Referência a validar"**:
foram registradas sem conferência contra os documentos oficiais. Valide cada uma e altere a situação para "Validada"
em `modules/backup/controls.py` antes de usá-las como evidência.

## Estrutura
```
app.py                  navegação e sessão
config/                 settings.py (variáveis de ambiente) e risk_methodology.py (metodologia versionada)
database/               connection, migrate, migrations/, seed, repositories/
models/                 constantes e dataclasses (Context, perfis, permissões)
modules/                registry.py e backup/ (perguntas, regras, controles, módulo)
services/               autenticação, visitante, autorização, ativos, avaliações, motores, tratamento, relatórios, auditoria
ui/                     components/ (estilo, widgets, formulários) e pages/
assets/                 styles/riskora.css e images/ (logotipo provisório)
scripts/                create_admin, load_demo, reset_demo, backup_db
tests/                  pytest
```

## Identidade visual
Cores da referência: bordô #6B1A2D, fundo #F7F4EF, cartão #FEFDF9, borda #E5E0D3, grafite #292929; a matriz de risco usa
os tons #E9E2D8, #D9C2C8, #B58090 e #6B1A2D. O tema fica em `.streamlit/config.toml` e o CSS em `assets/styles/riskora.css`.
Logotipos em `assets/images/`: `riskora_logo_clara.png` (para fundo bordô), `riskora_logo_bordo.png` (para fundo claro)
e `riskora_icone.png` (ícone da aba do navegador), gerados a partir dos arquivos oficiais enviados.
