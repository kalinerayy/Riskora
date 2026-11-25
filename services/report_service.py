"""Dashboard executivo e relatórios. Todos os números vêm do banco, escopados pela organização do contexto.

Regra dos totais atuais: vale a avaliação CONCLUÍDA mais recente de cada ativo. O histórico completo
(todas as versões concluídas) alimenta a evolução ao longo do tempo.
"""
from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

from config.risk_methodology import BASIS_LABELS, EVIDENCE_LABELS, INSUFFICIENT_DATA, RISK_BANDS, TREATMENT_REQUIRED_LEVELS
from database.repositories.assessments import AssessmentRepository
from database.repositories.assets import AssetRepository
from database.repositories.treatment import TreatmentRepository
from models.user import Context
from modules.registry import get_module_for_category
from services.assessment_service import AssessmentService
from services.audit_service import AuditService
from services.authorization_service import require
from services.privacy import person_label
from services.treatment_service import is_overdue, lifecycle

LEVELS = tuple(b[2] for b in RISK_BANDS) + (INSUFFICIENT_DATA,)

REPORT_KINDS = {
    "geral": "Relatório geral de riscos",
    "ativo": "Relatório por ativo",
    "categoria": "Relatório por categoria",
    "fragilidades": "Relatório de fragilidades",
    "controles": "Relatório de controles",
    "tratamento": "Relatório de planos de tratamento",
    "historico": "Histórico das avaliações",
    "evolucao": "Evolução da exposição a riscos",
}


@dataclass
class ReportFilters:
    date_from: str | None = None   # AAAA-MM-DD (data de conclusão da avaliação)
    date_to: str | None = None
    asset_id: int | None = None
    category_code: str | None = None
    owner: str | None = None       # responsável pelo ativo (contém)
    criticality: str | None = None  # nível do risco atual


@dataclass
class Report:
    kind: str
    title: str
    narrative: str
    rows: list = field(default_factory=list)


def _level_text(row) -> str:
    if not row:
        return "Sem reavaliação"
    return f"{row['level']} ({row['score']})" if row["score"] else row["level"]


def _safe_cell(value):
    """Mitiga injeção de fórmulas ao abrir o CSV em planilhas."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def to_csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    columns = [k for k in rows[0].keys() if not k.startswith("_")]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _safe_cell(row.get(k, "")) for k in columns})
    return buf.getvalue()


def _md_cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


class ReportService:
    def __init__(self, conn):
        self.conn = conn
        self.arepo = AssessmentRepository(conn)
        self.assets = AssetRepository(conn)
        self.trepo = TreatmentRepository(conn)
        self.asvc = AssessmentService(conn)
        self.audit = AuditService(conn)

    # -- base de dados dos relatórios ----------------------------------------------------------------
    def _risk_rows(self, ctx: Context) -> list[dict]:
        org = ctx.org_id
        concluded = {a["id"]: a for a in self.arepo.list_concluded(org)}
        rows = []
        for aid in self.arepo.latest_concluded_ids(org):
            a = concluded[aid]
            asset = self.assets.get_asset(org, a["asset_id"])
            for r in self.asvc.get_results(ctx, aid):
                cur = r["current"]
                rows.append({
                    "avaliacao_id": aid, "ativo_id": asset["id"], "codigo_ativo": asset["asset_code"],
                    "ativo": asset["name"], "categoria": asset["category_name"], "responsavel_ativo": asset["owner"],
                    "criticidade_ativo": asset["criticality"], "concluida_em": a["completed_at"] or "",
                    "regra": r["rule_code"], "fragilidade": r["title"], "base": BASIS_LABELS[r["basis"]],
                    "evidencia": EVIDENCE_LABELS[r["evidence_status"]],
                    "cenario_de_risco": r["scenario"], "risco_inerente": _level_text(r["inherent"]),
                    "risco_atual": _level_text(cur), "nivel_atual": cur["level"], "pontuacao_atual": cur["score"] or "",
                    "risco_residual": _level_text(r["residual"]),
                    "controles_recomendados": "; ".join(c["code"] for c in r["controls"]),
                    "acoes_registradas": len(r["actions"]), "limitacoes": r["limitations"],
                    "versao_metodologia": cur["methodology_version"], "versao_regras": a["rules_version"],
                    "versao_questionario": a["questionnaire_version"],
                    "_categoria_codigo": asset["category_code"], "_evidencia_status": r["evidence_status"],
                })
        return rows

    @staticmethod
    def _filter_rows(rows, f: ReportFilters):
        out = []
        for r in rows:
            day = (r.get("concluida_em") or "")[:10]
            if f.date_from and day < f.date_from:
                continue
            if f.date_to and day > f.date_to:
                continue
            if f.asset_id and r["ativo_id"] != f.asset_id:
                continue
            if f.category_code and r["_categoria_codigo"] != f.category_code:
                continue
            if f.owner and f.owner.lower() not in (r["responsavel_ativo"] or "").lower():
                continue
            if f.criticality and r["nivel_atual"] != f.criticality:
                continue
            out.append(r)
        return out

    def _action_rows(self, ctx: Context, f: ReportFilters) -> list[dict]:
        org = ctx.org_id
        ids = self.arepo.latest_concluded_ids(org)
        assets = {a["id"]: a for a in self.assets.list_assets(org)}
        rows = []
        for t in self.trepo.list_actions_for_assessments(org, ids):
            asset = assets.get(t["asset_id"], {})
            if f.asset_id and t["asset_id"] != f.asset_id:
                continue
            if f.category_code and asset.get("category_code") != f.category_code:
                continue
            if f.owner and f.owner.lower() not in (t["owner"] or "").lower():
                continue
            if f.date_from and (t["due_date"] or "9999") < f.date_from:
                continue
            if f.date_to and (t["due_date"] or "0000") > f.date_to:
                continue
            rows.append({"acao_id": t["id"], "ativo": t["asset_name"], "risco": t["risk_title"],
                         "acao": t["action"], "controle": t["control_code"] or "", "responsavel": t["owner"],
                         "prioridade": t["priority"], "prazo": t["due_date"] or "", "status": t["status"],
                         "ciclo": lifecycle(t), "vencida": "Sim" if is_overdue(t) else "Não",
                         "concluida_em": t["completed_at"] or "", "validada_em": (t["validated_at"] or "")[:10],
                         "evidencia_esperada": t["expected_evidence"]})
        return rows

    def controls_status(self, ctx: Context, assessment_ids) -> dict[str, dict]:
        """Por controle: quantos ativos o avaliaram e quantos têm deficiência (alguma fragilidade relacionada)."""
        require(ctx, "data:read")
        org = ctx.org_id
        stats: dict[str, dict] = {}
        for aid in assessment_ids:
            assessment = self.asvc._get(org, aid)
            module = self.asvc._module(assessment)
            answers = self.asvc._answers(org, aid)
            by_code = {q.code: q for q in module.questions}
            found = {f["rule_code"] for f in self.arepo.list_findings(org, aid)}
            rule_state = {}
            for rule in module.rules:
                evaluated = any(c in answers and by_code[c].is_visible(answers) for c in rule.question_codes)
                rule_state[rule.code] = (evaluated, rule.code in found)
            for control in module.controls:
                entry = stats.setdefault(control.code, {"name": control.name, "type": control.control_type,
                                                       "evaluated": set(), "deficient": set(),
                                                       "unvalidated_refs": sum(1 for r in control.references
                                                                               if r.validation_status != "Validada")})
                states = [rule_state[r] for r in control.addresses_rules if r in rule_state]
                if any(e for e, _ in states):
                    entry["evaluated"].add(assessment["asset_id"])
                if any(d for _, d in states):
                    entry["deficient"].add(assessment["asset_id"])
        return stats

    # -- dashboard ---------------------------------------------------------------------------------
    def compute_dashboard(self, ctx: Context) -> dict:
        require(ctx, "data:read")
        org = ctx.org_id
        assets = self.assets.list_assets(org)
        active = [a for a in assets if a["status"] != "Desativado"]
        latest = self.arepo.latest_concluded_ids(org)
        concluded = self.arepo.list_concluded(org)
        by_id = {a["id"]: a for a in concluded}
        assessed_assets = {by_id[i]["asset_id"] for i in latest}
        assessable = [a for a in active if get_module_for_category(a["category_code"])]
        pending = [a for a in assessable if a["id"] not in assessed_assets]
        drafts = self.arepo.list_drafts(org)
        incomplete = [d["id"] for d in drafts if not self.asvc.completeness_internal(org, d["id"]).complete]
        incomplete += [i for i in latest if not self.asvc.completeness_internal(org, i).complete]
        current = self.arepo.latest_by_kind(org, "current", latest)
        distribution = Counter({lvl: 0 for lvl in LEVELS})
        category_counts: Counter = Counter()
        for ra in current:
            distribution[ra["level"]] += 1
            category_counts[by_id[ra["assessment_id"]]["category_name"]] += 1
        findings = [f for aid in latest for f in self.arepo.list_findings(org, aid)]
        actions = self.trepo.list_actions_for_assessments(org, latest)
        ctrl = self.controls_status(ctx, latest)
        matrices = {}
        for kind in ("inherent", "current", "residual"):
            counts: Counter = Counter()
            for ra in self.arepo.latest_by_kind(org, kind, latest):
                if ra["probability"] and ra["impact"]:
                    counts[(ra["probability"], ra["impact"])] += 1
            matrices[kind] = dict(counts)
        all_ids = [a["id"] for a in concluded]
        high_by_assessment = Counter(ra["assessment_id"] for ra in self.arepo.latest_by_kind(org, "current", all_ids)
                                     if ra["level"] in TREATMENT_REQUIRED_LEVELS)
        evolution: dict[str, dict] = {}
        for a in concluded:
            month = (a["completed_at"] or "")[:7]
            if not month:
                continue
            row = evolution.setdefault(month, {"mes": month, "avaliacoes_concluidas": 0, "riscos_altos_ou_criticos": 0})
            row["avaliacoes_concluidas"] += 1
            row["riscos_altos_ou_criticos"] += high_by_assessment.get(a["id"], 0)
        return {
            "assets_total": len(assets), "assets_active": len(active), "assets_assessed": len(assessed_assets),
            "assessments_pending": len(pending), "assessments_incomplete": len(incomplete),
            "risks_total": len(current), "distribution": dict(distribution),
            "needs_treatment": sum(1 for ra in current if ra["level"] in TREATMENT_REQUIRED_LEVELS),
            "findings_total": len(findings),
            "insufficient_evidence": sum(1 for f in findings if f["evidence_status"] != "referenciada"),
            "controls_evaluated": sum(1 for c in ctrl.values() if c["evaluated"]),
            "controls_deficient": sum(1 for c in ctrl.values() if c["deficient"]),
            "actions_pending": sum(1 for t in actions if t["status"] in ("Não iniciado", "Em andamento", "Bloqueado")),
            "actions_overdue": sum(1 for t in actions if is_overdue(t)),
            "actions_done": sum(1 for t in actions if t["status"] == "Concluído"),
            "matrices": matrices, "risks_by_category": dict(category_counts),
            "recurring_weaknesses": Counter(f["title"] for f in findings).most_common(8),
            "treatment_lifecycle": dict(Counter(lifecycle(t) for t in actions)),
            "evolution": sorted(evolution.values(), key=lambda r: r["mes"]),
            "last_update": max((a["completed_at"] for a in concluded if a["completed_at"]), default=None),
        }

    def priority_recommendations(self, ctx: Context, limit: int = 5) -> list[dict]:
        """Riscos mais graves das avaliações vigentes, com a primeira ação sugerida do controle recomendado."""
        require(ctx, "data:read")
        catalog = {c["code"]: c for c in self.arepo.list_controls()}
        rows = sorted(self._risk_rows(ctx), key=lambda r: r["pontuacao_atual"] or 0, reverse=True)[:limit]
        out = []
        for r in rows:
            code = (r["controles_recomendados"].split(";")[0] or "").strip()
            actions = (catalog.get(code, {}).get("implementation_actions") or "").splitlines()
            out.append({"ativo": r["ativo"], "fragilidade": r["fragilidade"], "nivel": r["nivel_atual"],
                        "pontuacao": r["pontuacao_atual"], "controle": code, "acao": actions[0] if actions else ""})
        return out

    # -- relatórios ---------------------------------------------------------------------------------
    def build_report(self, ctx: Context, kind: str, filters: ReportFilters | None = None) -> Report:
        require(ctx, "data:read")
        if kind not in REPORT_KINDS:
            raise ValueError("Tipo de relatório inválido.")
        f = filters or ReportFilters()
        title = REPORT_KINDS[kind]
        if kind in ("geral", "ativo", "categoria", "fragilidades", "controles", "evolucao"):
            risks = self._filter_rows(self._risk_rows(ctx), f)
        if kind == "geral":
            counts = Counter(r["nivel_atual"] for r in risks)
            top = Counter(r["fragilidade"] for r in risks).most_common(3)
            text = (f"{len(risks)} risco(s) nas avaliações vigentes. Distribuição do risco atual: "
                    + (", ".join(f"{k}: {v}" for k, v in counts.items()) or "sem riscos") + ". "
                    + ("Fragilidades mais frequentes: " + "; ".join(f"{t} ({n})" for t, n in top) + ". " if top else "")
                    + "Cada risco parte de respostas declaradas e deve ser confirmado com evidências.")
            return Report(kind, title, text, risks)
        if kind == "ativo":
            groups: dict = defaultdict(list)
            for r in risks:
                groups[(r["ativo_id"], r["codigo_ativo"], r["ativo"])].append(r)
            rows = []
            for (aid, code, name), items in groups.items():
                lv = Counter(i["nivel_atual"] for i in items)
                rows.append({"codigo_ativo": code, "ativo": name, "categoria": items[0]["categoria"],
                             "riscos": len(items), "criticos": lv.get("Crítico", 0), "altos": lv.get("Alto", 0),
                             "moderados": lv.get("Moderado", 0), "baixos": lv.get("Baixo", 0),
                             "dados_insuficientes": lv.get(INSUFFICIENT_DATA, 0),
                             "concluida_em": items[0]["concluida_em"][:10]})
            worst = max(rows, key=lambda r: (r["criticos"], r["altos"]), default=None)
            text = f"{len(rows)} ativo(s) com riscos nas avaliações vigentes."
            if worst:
                text += f" O ativo com mais riscos críticos/altos é {worst['ativo']} ({worst['criticos']} crítico(s), {worst['altos']} alto(s))."
            return Report(kind, title, text, rows)
        if kind == "categoria":
            groups = defaultdict(list)
            for r in risks:
                groups[r["categoria"]].append(r)
            rows = [{"categoria": cat, "ativos_com_riscos": len({i["ativo_id"] for i in items}), "riscos": len(items),
                     "criticos_ou_altos": sum(1 for i in items if i["nivel_atual"] in TREATMENT_REQUIRED_LEVELS)}
                    for cat, items in groups.items()]
            return Report(kind, title, f"Riscos distribuídos em {len(rows)} categoria(s) de ativos com avaliação disponível.", rows)
        if kind == "fragilidades":
            groups = defaultdict(list)
            for r in risks:
                groups[(r["regra"], r["fragilidade"])].append(r)
            rank = {lvl: i for i, lvl in enumerate(reversed(LEVELS))}
            rows = [{"regra": code, "fragilidade": name, "ativos_afetados": len({i["ativo_id"] for i in items}),
                     "pior_nivel": max(items, key=lambda i: rank.get(i["nivel_atual"], 0))["nivel_atual"],
                     "sem_evidencia_referenciada": sum(1 for i in items if i["_evidencia_status"] != "referenciada")}
                    for (code, name), items in sorted(groups.items())]
            return Report(kind, title, f"{len(rows)} tipo(s) de fragilidade potencial. Fragilidades sem evidência "
                          "referenciada dependem apenas de declaração ou de lacuna de conhecimento.", rows)
        if kind == "controles":
            ids = [a for a in {r["avaliacao_id"] for r in risks}] if (f.asset_id or f.category_code or f.owner or f.criticality or f.date_from or f.date_to) else self.arepo.latest_concluded_ids(ctx.org_id)
            stats = self.controls_status(ctx, ids)
            rows = [{"controle": code, "nome": s["name"], "tipo": s["type"], "ativos_avaliados": len(s["evaluated"]),
                     "ativos_com_deficiencia": len(s["deficient"]),
                     "referencias_a_validar": s["unvalidated_refs"]} for code, s in sorted(stats.items())]
            return Report(kind, title, "Um controle é considerado avaliado quando ao menos uma pergunta relacionada foi "
                          "respondida, e com deficiência quando há fragilidade potencial relacionada. Referências "
                          "marcadas como 'a validar' ainda não foram verificadas nas fontes oficiais.", rows)
        if kind == "tratamento":
            rows = self._action_rows(ctx, f)
            overdue = sum(1 for r in rows if r["vencida"] == "Sim")
            text = (f"{len(rows)} ação(ões) de tratamento, {overdue} vencida(s). Concluir uma ação não reduz o risco: "
                    "a redução só vale após reavaliação documentada (risco residual).")
            return Report(kind, title, text, rows)
        if kind == "historico":
            rows = []
            for a in self.arepo.list_assessments(ctx.org_id, f.asset_id):
                day = (a["completed_at"] or a["created_at"])[:10]
                if (f.date_from and day < f.date_from) or (f.date_to and day > f.date_to):
                    continue
                rows.append({"avaliacao_id": a["id"], "ativo": a["asset_name"], "situacao": a["status"],
                             "avaliador": person_label(ctx, a["assessor_name"]), "iniciada_em": a["created_at"][:10],
                             "concluida_em": (a["completed_at"] or "")[:10], "origem": a["parent_assessment_id"] or "",
                             "versao_metodologia": a["methodology_version"],
                             "versao_questionario": a["questionnaire_version"], "versao_regras": a["rules_version"]})
            return Report(kind, title, f"{len(rows)} avaliação(ões) registrada(s). Nenhuma versão anterior é sobrescrita.", rows)
        # evolucao
        dash = self.compute_dashboard(ctx)
        rows = dash["evolution"]
        return Report(kind, title, "Série mensal calculada a partir de todas as avaliações concluídas. Compare "
                      "avaliações feitas com a mesma versão de metodologia.", rows)

    # -- exportação ---------------------------------------------------------------------------------
    def log_export(self, ctx: Context, kind: str, fmt: str, entity_id: int | None = None) -> None:
        """Registra na auditoria que um relatório foi baixado (chamado quando o usuário clica em baixar)."""
        require(ctx, "report:export")
        with self.conn:
            self.audit.log_ctx(ctx, "report_exported", "report", entity_id, f"{kind};{fmt}")

    def csv_text(self, ctx: Context, report: Report) -> str:
        require(ctx, "report:export")
        return to_csv(report.rows)

    def markdown_text(self, ctx: Context, report: Report, organization_name: str = "") -> str:
        require(ctx, "report:export")
        lines = [f"# {report.title}", ""]
        if organization_name:
            lines += [f"Organização: {organization_name} | Gerado em {date.today().isoformat()}", ""]
        lines += [report.narrative, ""]
        if report.rows:
            cols = [k for k in report.rows[0] if not k.startswith("_")]
            lines.append("| " + " | ".join(cols) + " |")
            lines.append("|" + "---|" * len(cols))
            for row in report.rows:
                lines.append("| " + " | ".join(_md_cell(row.get(c, "")) for c in cols) + " |")
            lines.append("")
        else:
            lines += ["Sem registros para os filtros selecionados.", ""]
        return "\n".join(lines)

    def asset_report_markdown(self, ctx: Context, asset_id: int) -> str:
        """Relatório individual do ativo, com explicação textual de cada risco da última avaliação concluída."""
        require(ctx, "report:export")
        asset = self.assets.get_asset(ctx.org_id, asset_id)
        if not asset:
            raise ValueError("Ativo não encontrado.")
        lines = [f"# Relatório do ativo {asset['asset_code']} - {asset['name']}", "",
                 f"Categoria: {asset['category_name']} | Criticidade: {asset['criticality']} | Status: {asset['status']}", ""]
        latest = self.arepo.latest_concluded_for_asset(ctx.org_id, asset_id)
        if not latest:
            lines.append("Este ativo ainda não possui avaliação concluída.")
        else:
            comp = self.asvc.completeness_internal(ctx.org_id, latest["id"])
            lines += [f"Avaliação #{latest['id']} concluída em {(latest['completed_at'] or '')[:10]} "
                      f"(metodologia v{latest['methodology_version']}, questionário v{latest['questionnaire_version']}, "
                      f"regras v{latest['rules_version']}). Preenchimento: {comp.percent}%"
                      + ("" if comp.complete else " **(AVALIAÇÃO INCOMPLETA)**"), ""]
            results = self.asvc.get_results(ctx, latest["id"])
            if not results:
                lines.append("Nenhuma fragilidade potencial foi identificada nas respostas. Isso não comprova ausência de risco.")
            for r in results:
                cur = r["current"]
                lines += [f"## {r['rule_code']} - {r['title']}", "", r["explanation"], "",
                          f"- **Fragilidade potencial:** {r['weakness']}", f"- **Cenário de risco:** {r['scenario']}",
                          f"- **Consequências possíveis:** {r['consequences']}",
                          f"- **Justificativa de probabilidade:** {cur['probability_justification']}",
                          f"- **Justificativa de impacto:** {cur['impact_justification']}",
                          f"- **Risco inerente:** {_level_text(r['inherent'])} | **atual:** {_level_text(cur)} | "
                          f"**residual:** {_level_text(r['residual'])}",
                          "- **Controles recomendados:** " + (", ".join(f"{c['code']} ({c['name']})" for c in r["controls"]) or "-"),
                          f"- **Ações registradas:** {len(r['actions'])}", f"- **Limitações:** {r['limitations']}"]
                if cur["notes"]:
                    lines.append(f"- **Incertezas:** {cur['notes']}")
                lines.append("")
        return "\n".join(lines)
