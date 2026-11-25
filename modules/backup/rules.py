"""Regras de diagnóstico do módulo de backup.

As regras são DADOS (DiagnosticRule), não código: o motor em services/diagnostic_engine.py
as avalia sem conhecer o conteúdo. Para ampliar, adicione regras e incremente RULES_VERSION.
Todas as conclusões partem de respostas declaradas e têm limitações explícitas.
"""
from models.risk import DiagnosticRule

RULES_VERSION = "1.0.0"

_ALL = ("nao", "parcial", "nao_sei")
_STD_DIMS = ("availability", "integrity", "operational", "financial", "legal")
_P_NOTE = ("A probabilidade atual segue a base da conclusão: lacuna declarada = 4, controle parcial = 3, "
           "lacuna de conhecimento = 3 (provisória).")
_I_NOTE = ("O impacto é herdado do ativo avaliado: maior valor entre as dimensões relevantes ao cenário "
           "(%s). Se o ativo não tiver impactos informados, o resultado é 'Dados insuficientes'.")

RULES = (
    DiagnosticRule(
        code="BK-001", title="Ausência ou insuficiência de testes de restauração",
        triggers={"Q10": _ALL, "Q10A": ("nao", "nao_sei")},
        weakness="A capacidade de recuperação dos dados não foi validada por testes periódicos documentados.",
        evidence_description="Respostas a Q10 (testes periódicos) e, quando aplicável, Q10A (resultado do último teste).",
        risk_scenario="Após perda de dados, falha operacional ou ataque, a organização pode não conseguir "
                      "recuperar as informações dentro do prazo necessário.",
        consequences="Indisponibilidade de sistemas, interrupção de operações, custos de recuperação e perdas financeiras.",
        probability_criteria="Sem teste, falhas silenciosas (mídia corrompida, cópia incompleta, procedimento "
                             "desconhecido) permanecem possíveis. " + _P_NOTE,
        impact_criteria=_I_NOTE % "disponibilidade, integridade, operacional, financeiro, legal",
        impact_dimensions=_STD_DIMS,
        control_codes=("RC-BK-09", "RC-BK-10", "RC-BK-11"),
        references=("CIS Controls v8.1 - Controle 11 (Recuperação de Dados) [a validar]",
                    "NIST CSF 2.0 - PR.DS-11 [a validar]"),
    ),
    DiagnosticRule(
        code="BK-002", title="Ausência de cópia isolada",
        triggers={"Q06": _ALL},
        weakness="As cópias podem estar expostas ao comprometimento do ambiente principal.",
        evidence_description="Resposta a Q06 sobre cópia isolada ou mecanismo equivalente.",
        risk_scenario="Um invasor ou incidente com privilégios suficientes pode comprometer simultaneamente "
                      "os dados de produção e suas cópias de recuperação.",
        consequences="Perda simultânea de dados e cópias, indisponibilidade prolongada e dependência de "
                     "recuperação externa ou de reconstrução.",
        probability_criteria="Cópias alcançáveis a partir da produção ampliam a chance de perda conjunta. " + _P_NOTE,
        impact_criteria=_I_NOTE % "disponibilidade, integridade, operacional, financeiro",
        impact_dimensions=("availability", "integrity", "operational", "financial"),
        control_codes=("RC-BK-05", "RC-BK-06", "RC-BK-07"),
        references=("CIS Controls v8.1 - Salvaguarda 11.4 [a validar]", "NIST CSF 2.0 - PR.DS-11 [a validar]"),
        limitations="Resposta 'Não sei' indica falta de informação, não ausência confirmada da cópia isolada. "
                    "Conclusão baseada em declaração; não houve verificação técnica da arquitetura.",
    ),
    DiagnosticRule(
        code="BK-003", title="Falhas de monitoramento das rotinas de backup",
        triggers={"Q09": _ALL},
        weakness="Falhas de execução podem permanecer sem tratamento.",
        evidence_description="Resposta a Q09 sobre acompanhamento de resultados e tratamento de falhas.",
        risk_scenario="A organização pode descobrir que não possui uma cópia recuperável somente quando "
                      "precisar restaurar os dados.",
        consequences="Perda de dados não percebida, indisponibilidade e custos de recuperação.",
        probability_criteria="Sem acompanhamento, falhas repetidas podem acumular-se sem detecção. " + _P_NOTE,
        impact_criteria=_I_NOTE % "disponibilidade, integridade, operacional, financeiro, legal",
        impact_dimensions=_STD_DIMS,
        control_codes=("RC-BK-08", "RC-BK-11"),
        references=("CIS Controls v8.1 - Salvaguarda 11.2 [a validar]", "NIST CSF 2.0 - PR.DS-11 [a validar]"),
    ),
    DiagnosticRule(
        code="BK-004", title="Cobertura insuficiente dos ativos críticos",
        triggers={"Q02": _ALL},
        weakness="Parte das informações relevantes pode não estar protegida por backup.",
        evidence_description="Resposta a Q02 sobre a cobertura dos ativos críticos.",
        risk_scenario="Uma falha pode causar perda de dados sem que exista cópia adequada para recuperação.",
        consequences="Perda permanente de dados críticos, interrupção de processos e perdas financeiras.",
        probability_criteria="Ativos sem cópia, ou com cobertura não confirmada, não têm caminho de recuperação "
                             "garantido. " + _P_NOTE,
        impact_criteria=_I_NOTE % "disponibilidade, integridade, operacional, financeiro, legal",
        impact_dimensions=_STD_DIMS,
        control_codes=("RC-BK-02", "RC-BK-10"),
        references=("CIS Controls v8.1 - Salvaguarda 1.1 [a validar]", "NIST CSF 2.0 - ID.AM-01 [a validar]"),
    ),
    DiagnosticRule(
        code="BK-005", title="Controle de acesso insuficiente aos backups",
        triggers={"Q08": _ALL},
        weakness="Usuários ou serviços podem alterar, excluir ou acessar cópias indevidamente.",
        evidence_description="Resposta a Q08 sobre restrição de acesso às cópias.",
        risk_scenario="Comprometimento ou exposição de dados e perda da capacidade de recuperação.",
        consequences="Vazamento de dados contidos nas cópias, exclusão ou adulteração de cópias e "
                     "indisponibilidade na recuperação.",
        probability_criteria="Acesso amplo às cópias ou às ferramentas de backup aumenta a superfície de "
                             "abuso e erro. " + _P_NOTE,
        impact_criteria=_I_NOTE % "todas as dimensões, incluindo confidencialidade",
        impact_dimensions=("availability", "integrity", "confidentiality", "operational", "financial", "legal"),
        control_codes=("RC-BK-07", "RC-BK-11"),
        references=("CIS Controls v8.1 - Salvaguarda 6.8 [a validar]", "NIST CSF 2.0 - PR.AA-05 [a validar]"),
        limitations="Sem evidência de permissões (listas de acesso, revisões), a conclusão não confirma "
                    "acesso indevido real. Não houve verificação técnica.",
    ),
    DiagnosticRule(
        code="BK-006", title="Ausência de política ou procedimento de backup",
        triggers={"Q01": _ALL},
        weakness="O processo de backup pode depender de práticas informais e sem responsáveis definidos.",
        evidence_description="Resposta a Q01 sobre política ou procedimento documentado.",
        risk_scenario="Rotinas inconsistentes, ausência de responsável e falhas de continuidade quando "
                      "pessoas-chave estiverem indisponíveis.",
        consequences="Cobertura irregular, retenção inadequada e recuperação lenta ou incorreta.",
        probability_criteria="Processos sem documentação tendem a variar entre pessoas e ao longo do tempo. " + _P_NOTE,
        impact_criteria=_I_NOTE % "disponibilidade, integridade, operacional, financeiro, legal",
        impact_dimensions=_STD_DIMS,
        control_codes=("RC-BK-01",),
        references=("NIST CSF 2.0 - GV.PO-01 [a validar]", "ISO/IEC 27002:2022 - 8.13 [a validar]"),
    ),
    DiagnosticRule(
        code="BK-007", title="Frequência ou automação inadequadas",
        triggers={"Q03": _ALL, "Q04": _ALL},
        weakness="A frequência pode não refletir a perda de dados tolerável, ou a execução pode depender de "
                 "ação manual e de detecção falha.",
        evidence_description="Respostas a Q03 (frequência) e Q04 (automação e identificação de falhas).",
        risk_scenario="Em caso de perda, os dados mais recentes podem estar além do tolerável, ou execuções "
                      "podem ser omitidas sem percepção.",
        consequences="Perda de dados superior ao aceitável, retrabalho e interrupção de operações.",
        probability_criteria="Frequência desalinhada e execução manual aumentam a chance de lacunas no histórico. " + _P_NOTE,
        impact_criteria=_I_NOTE % "disponibilidade, integridade, operacional, financeiro, legal",
        impact_dimensions=_STD_DIMS,
        control_codes=("RC-BK-03", "RC-BK-08"),
        references=("CIS Controls v8.1 - Salvaguarda 11.2 [a validar]",),
    ),
    DiagnosticRule(
        code="BK-008", title="Retenção não definida ou inadequada",
        triggers={"Q05": _ALL},
        weakness="O histórico de cópias pode não permitir recuperar versões anteriores necessárias.",
        evidence_description="Resposta a Q05 sobre período de retenção.",
        risk_scenario="Corrupção ou exclusão percebida tardiamente pode já ter sobrescrito todas as cópias válidas.",
        consequences="Impossibilidade de recuperar versões íntegras e eventual descumprimento de requisitos "
                     "de guarda.",
        probability_criteria="Retenção curta ou indefinida reduz a janela para recuperar versões íntegras. " + _P_NOTE,
        impact_criteria=_I_NOTE % "disponibilidade, integridade, operacional, financeiro, legal",
        impact_dimensions=_STD_DIMS,
        control_codes=("RC-BK-04",),
        references=("CIS Controls v8.1 - Salvaguarda 11.1 [a validar]", "ISO/IEC 27002:2022 - 8.13 [a validar]"),
    ),
    DiagnosticRule(
        code="BK-009", title="Ausência de proteção contra alteração e exclusão (imutabilidade)",
        triggers={"Q07": _ALL},
        weakness="As cópias podem ser alteradas ou apagadas por conta comprometida, erro ou malware.",
        evidence_description="Resposta a Q07 sobre mecanismos contra alteração e exclusão indevidas.",
        risk_scenario="Um ataque de ransomware ou uma conta privilegiada comprometida pode criptografar ou "
                      "apagar as cópias de recuperação.",
        consequences="Perda das cópias, dependência de resgate ou reconstrução e indisponibilidade prolongada.",
        probability_criteria="Cópias graváveis e removíveis a partir de contas comuns são alvo típico de "
                             "ataques destrutivos. " + _P_NOTE,
        impact_criteria=_I_NOTE % "disponibilidade, integridade, operacional, financeiro, legal",
        impact_dimensions=_STD_DIMS,
        control_codes=("RC-BK-06", "RC-BK-05", "RC-BK-07"),
        references=("CIS Controls v8.1 - Salvaguarda 11.3 [a validar]", "NIST CSF 2.0 - PR.DS-11 [a validar]"),
        limitations="Conclusão baseada em declaração; não houve verificação de configuração técnica "
                    "(por exemplo, bloqueio de objetos).",
    ),
    DiagnosticRule(
        code="BK-010", title="Objetivos de recuperação (RTO/RPO) não definidos",
        triggers={"Q11": _ALL},
        weakness="Não há metas de tempo e de perda de dados que orientem o desenho do backup e da recuperação.",
        evidence_description="Resposta a Q11 sobre RTO e RPO (quando aplicáveis).",
        risk_scenario="A organização pode descobrir, durante um incidente, que sua capacidade de recuperação "
                      "é incompatível com a necessidade do negócio.",
        consequences="Indisponibilidade acima do tolerável e decisões de recuperação sem critério.",
        probability_criteria="Sem metas, a frequência e a técnica de backup podem não corresponder à necessidade. " + _P_NOTE,
        impact_criteria=_I_NOTE % "disponibilidade, operacional, financeiro, legal",
        impact_dimensions=("availability", "operational", "financial", "legal"),
        control_codes=("RC-BK-10", "RC-BK-03"),
        references=("NIST CSF 2.0 - RC.RP-01 [a validar]", "ISO/IEC 27002:2022 - 5.30 [a validar]"),
        limitations="RTO e RPO podem não se aplicar a todos os ativos; a regra não conclui que a ausência "
                    "seja inadequada para o ativo avaliado.",
    ),
    DiagnosticRule(
        code="BK-011", title="Evidências insuficientes da execução e dos testes",
        triggers={"Q12": _ALL},
        weakness="As afirmações sobre backups e testes não podem ser comprovadas por registros.",
        evidence_description="Resposta a Q12 sobre registros de execução e de testes.",
        risk_scenario="Falhas recorrentes ou ausência de testes podem passar despercebidas e não haver base "
                      "para auditoria ou melhoria.",
        consequences="Dificuldade de demonstrar controle, de investigar falhas e de atender auditorias.",
        probability_criteria="Sem registros, não é possível confirmar eficácia nem detectar tendências. " + _P_NOTE,
        impact_criteria=_I_NOTE % "operacional, financeiro, legal",
        impact_dimensions=("operational", "financial", "legal"),
        control_codes=("RC-BK-11",),
        references=("ISO/IEC 27002:2022 - 8.13 [a validar]", "NIST CSF 2.0 - PR.DS-11 [a validar]"),
    ),
)

RULES_BY_CODE = {r.code: r for r in RULES}
