"""Questionário do módulo Backup e Recuperação de Dados.

Cada pergunta pertence a um domínio de controle e tem uma finalidade diagnóstica.
Para ampliar: adicione novos objetos Question e incremente QUESTIONNAIRE_VERSION.
"""
from models.assessment import Question

TEMPLATE_CODE = "BK"
TEMPLATE_NAME = "Backup e Recuperação de Dados"
AREA_CODE = "TI"
QUESTIONNAIRE_VERSION = "1.0.0"

DOMAINS = {
    1: "Política e responsabilidades de backup",
    2: "Cobertura dos ativos críticos",
    3: "Frequência e automação",
    4: "Retenção e histórico das cópias",
    5: "Armazenamento e segregação",
    6: "Proteção contra exclusão, alteração e ransomware",
    7: "Controle de acesso aos backups",
    8: "Monitoramento e falhas nas rotinas",
    9: "Testes de restauração",
    10: "Recuperação e continuidade operacional",
    11: "Documentação e evidências",
}


def _q(code, domain_no, text, purpose, parent=None, parent_answers=()):
    return Question(code, domain_no, DOMAINS[domain_no], text, purpose, parent, tuple(parent_answers))


QUESTIONS = (
    _q("Q01", 1, "Existe uma política ou procedimento documentado de backup?",
       "Verificar se há diretriz formal e responsáveis definidos para o processo."),
    _q("Q02", 2, "Todos os ativos considerados críticos estão contemplados no processo de backup?",
       "Identificar ativos críticos sem cópia ou com cobertura não confirmada."),
    _q("Q03", 3, "A frequência dos backups está definida de acordo com a necessidade do negócio?",
       "Verificar o alinhamento entre a frequência das cópias e a perda de dados tolerável."),
    _q("Q04", 3, "Os backups são executados automaticamente e as falhas são identificadas?",
       "Reduzir dependência de execução manual e detectar falhas de execução."),
    _q("Q05", 4, "O período de retenção das cópias está definido e atende aos requisitos do negócio?",
       "Verificar se há histórico suficiente para recuperar versões anteriores."),
    _q("Q06", 5, "Existe uma cópia isolada do ambiente principal ou protegida contra comprometimento "
                 "do ambiente de produção?",
       "Avaliar se um comprometimento do ambiente principal alcançaria também as cópias."),
    _q("Q07", 6, "Há mecanismos adequados para impedir ou limitar a alteração ou exclusão indevida "
                 "de cópias?",
       "Avaliar a proteção das cópias contra alteração e exclusão (inclusive por ransomware)."),
    _q("Q08", 7, "O acesso aos backups é restrito a pessoas e serviços autorizados?",
       "Verificar aplicação de menor privilégio sobre as cópias e sobre as ferramentas de backup."),
    _q("Q09", 8, "A organização acompanha os resultados das rotinas e trata falhas de backup?",
       "Verificar se falhas de execução são detectadas e tratadas em tempo útil."),
    _q("Q10", 9, "Existem testes periódicos de restauração documentados?",
       "Verificar se a capacidade de recuperação foi validada, mesmo quando os backups rodam regularmente."),
    _q("Q10A", 9, "O último teste de restauração recuperou os dados com sucesso e dentro do tempo esperado?",
       "Avaliar o resultado dos testes, e não apenas a sua existência.",
       parent="Q10", parent_answers=("sim", "parcial")),
    _q("Q11", 10, "Existem objetivos de recuperação definidos para os ativos relevantes, como RTO e RPO, "
                  "quando aplicáveis?",
       "Verificar se há metas de tempo e de perda de dados que orientem o backup e a recuperação."),
    _q("Q12", 11, "Existem registros que demonstrem a execução dos backups e os resultados dos testes "
                  "de recuperação?",
       "Verificar se as afirmações podem ser comprovadas por evidências."),
)

QUESTIONS_BY_CODE = {q.code: q for q in QUESTIONS}
