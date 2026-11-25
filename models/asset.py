"""Constantes de ativos e das categorias de ativos suportadas pela estrutura."""

# (código, nome). Somente categorias com módulo registrado em modules/registry.py permitem avaliação.
ASSET_CATEGORIES = (
    ("infraestrutura_servidores", "Infraestrutura e servidores"),
    ("backup_recuperacao", "Backup e recuperação de dados"),
    ("aplicacoes_web_apis", "Aplicações web e APIs"),
    ("bancos_de_dados", "Bancos de dados"),
    ("sistemas_corporativos", "Sistemas corporativos"),
    ("identidade_acessos", "Identidade e controle de acessos"),
    ("email_colaboracao", "E-mail e ferramentas de colaboração"),
    ("endpoints", "Endpoints"),
    ("nuvem", "Computação em nuvem"),
    ("fornecedores_terceiros", "Fornecedores e terceiros"),
    ("ambientes_desenvolvimento", "Ambientes de desenvolvimento"),
)
CRITICALITY_LEVELS = ("Desconhecida", "Baixa", "Média", "Alta", "Crítica")
CLASSIFICATIONS = ("Não informada", "Pública", "Interna", "Confidencial", "Restrita")
AVAILABILITY_REQUIREMENTS = ("Não informado", "Baixa", "Média", "Alta", "Contínua (24x7)")
ASSET_STATUSES = ("Ativo", "Em implantação", "Desativado")
IMPACT_FIELDS = ("impact_availability", "impact_integrity", "impact_confidentiality", "impact_operational",
                 "impact_financial", "impact_legal")
