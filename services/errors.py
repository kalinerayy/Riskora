"""Erros de regra de negócio. As mensagens são seguras para exibir ao usuário (sem detalhes internos)."""


class RiskoraError(ValueError):
    """Erro de regra de negócio ou de validação."""


class PermissionDenied(RiskoraError):
    """O perfil do usuário não permite a operação."""


class NotFoundError(RiskoraError):
    """Registro inexistente OU pertencente a outra organização (a mensagem não distingue os casos)."""


class AuthenticationError(RiskoraError):
    """Falha de autenticação (mensagem genérica, sem revelar se o e-mail existe)."""
