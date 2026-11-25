"""Configuração centralizada da metodologia de risco da Riskora.

Estes critérios são os parâmetros INICIAIS da metodologia da Riskora, inspirados em boas práticas de
gestão de riscos (por exemplo, o processo descrito na ISO 31000). Não são prescritos nem certificados
por nenhuma norma e devem ser aprovados e adaptados pela organização.

Para alterar um limite, edite este arquivo e incremente METHODOLOGY_VERSION:
cada avaliação grava a versão usada, o que permite distinguir resultados antigos.
"""
from __future__ import annotations

METHODOLOGY_VERSION = "1.0.0"

METHODOLOGY_NOTICE = (
    "Parâmetros iniciais da metodologia da Riskora. Não são exigências universais "
    "de ISO, NIST ou CIS e devem ser aprovados e adaptados pela organização."
)

# --- Respostas do questionário -------------------------------------------------
ANSWER_OPTIONS = {
    "sim": "Sim",
    "parcial": "Parcialmente",
    "nao": "Não",
    "nao_sei": "Não sei",
    "nao_se_aplica": "Não se aplica",
}

# --- Escalas -------------------------------------------------------------------
PROBABILITY_SCALE = {
    1: ("Muito baixa", "Cenário improvável: controles eficazes e comprovados por evidências, "
                       "sem histórico de falhas e com baixa exposição."),
    2: ("Baixa", "Controles existentes com poucas lacunas conhecidas; falhas raras ou sem histórico."),
    3: ("Moderada", "Controles parciais ou não comprovados; lacunas conhecidas ou falta de informação "
                    "que impede afastar o cenário."),
    4: ("Alta", "Controle declarado como inexistente; condições que favorecem o cenário estão presentes."),
    5: ("Muito alta", "Condições favoráveis ao cenário, exposição elevada e histórico recorrente de falhas "
                      "ou incidentes (exige informação que o questionário inicial não coleta)."),
}

IMPACT_SCALE = {
    1: ("Insignificante", "Sem efeito perceptível nas operações, nos dados ou nas obrigações."),
    2: ("Pequeno", "Efeito localizado e facilmente absorvido; recuperação rápida e de baixo custo."),
    3: ("Moderado", "Interrupção ou perda relevante em um processo; custos e esforço de recuperação sensíveis."),
    4: ("Alto", "Interrupção prolongada de processos importantes, perdas financeiras ou descumprimento "
                "de obrigações relevantes."),
    5: ("Crítico", "Paralisação de processos essenciais, perda irreversível de informações críticas ou "
                   "consequências legais/contratuais graves."),
}

IMPACT_DIMENSIONS = {
    "availability": "Disponibilidade",
    "integrity": "Integridade",
    "confidentiality": "Confidencialidade",
    "operational": "Impacto operacional",
    "financial": "Impacto financeiro",
    "legal": "Obrigações legais e contratuais",
}

IMPACT_CONSOLIDATION_RULE = (
    "O impacto consolidado de um risco é o MAIOR valor entre as dimensões relevantes ao cenário "
    "(critério conservador). Não se usa média, para que um impacto crítico em uma dimensão não seja "
    "diluído por dimensões menos afetadas. Dimensões relevantes não informadas são listadas como "
    "incerteza; se nenhuma estiver informada, o resultado é 'Dados insuficientes'."
)

# --- Classificação -------------------------------------------------------------
# (mínimo, máximo, rótulo). Risco = Probabilidade x Impacto (1 a 25).
RISK_BANDS = (
    (1, 4, "Baixo"),
    (5, 9, "Moderado"),
    (10, 16, "Alto"),
    (17, 25, "Crítico"),
)

INSUFFICIENT_DATA = "Dados insuficientes"

# Níveis que, nesta configuração inicial, exigem decisão de tratamento.
TREATMENT_REQUIRED_LEVELS = ("Alto", "Crítico")

# --- Probabilidade: regras explicáveis ----------------------------------------
# A probabilidade ATUAL é derivada da base da conclusão (nunca "sorteada").
# Cada entrada: (nível de probabilidade, texto do critério mostrado ao usuário).
BASIS_PROBABILITY = {
    "declared_gap": (4, "O controle foi declarado como inexistente; as condições que favorecem o cenário "
                        "estão presentes (nível 4 - Alta)."),
    "partial": (3, "O controle foi declarado como parcial; a proteção existe, mas com lacunas "
                   "(nível 3 - Moderada)."),
    "knowledge_gap": (3, "Não há informação para confirmar o controle; a estimativa é PROVISÓRIA "
                         "(nível 3 - Moderada) e deve ser confirmada com evidências."),
}

# Probabilidade INERENTE padrão: cenário considerado sem nenhum controle existente.
DEFAULT_INHERENT_PROBABILITY = 4

BASIS_LABELS = {
    "declared_gap": "Lacuna declarada",
    "partial": "Controle parcial",
    "knowledge_gap": "Lacuna de conhecimento ou de evidência",
}

EVIDENCE_LABELS = {
    "referenciada": "Evidência referenciada",
    "apenas_declarada": "Apenas declarada (sem evidência referenciada)",
    "lacuna_de_conhecimento": "Lacuna de conhecimento",
}

RISK_KINDS = {
    "inherent": "Inerente (antes dos controles existentes)",
    "current": "Atual (considerando controles e evidências disponíveis)",
    "residual": "Residual (após tratamento e reavaliação documentada)",
}

LEVEL_COLORS = {"Baixo": "green", "Moderado": "yellow", "Alto": "orange", "Crítico": "red"}
