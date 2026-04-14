"""Repository for email templates."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.exceptions import InvalidStateError, ResourceNotFoundError
from ..db.models import EmailTemplate


class EmailTemplateRepository:
    """Manages retrieval and maintenance of email templates."""

    def __init__(self, session: Session):
        self._session = session

    def get(self, template_id: str) -> EmailTemplate:
        entity = self._session.get(EmailTemplate, template_id)
        if entity is None:
            raise ResourceNotFoundError(f"Email template '{template_id}' was not found")
        return entity

    def get_by_code(self, template_code: str) -> EmailTemplate:
        stmt = select(EmailTemplate).where(EmailTemplate.template_code == template_code)
        entity = self._session.execute(stmt).scalar_one_or_none()
        if entity is None:
            raise ResourceNotFoundError(f"Email template '{template_code}' was not found")
        return entity

    def list_active(self, *, scene: str | None = None) -> list[EmailTemplate]:
        stmt = select(EmailTemplate).where(EmailTemplate.status == "active")
        if scene is not None:
            stmt = stmt.where(EmailTemplate.scene == scene)
        stmt = stmt.order_by(EmailTemplate.is_default.desc(), EmailTemplate.updated_at.desc())
        return list(self._session.execute(stmt).scalars().all())

    def create(
        self,
        *,
        template_code: str,
        template_name: str,
        subject_template: str,
        html_template: str | None,
        text_template: str | None,
        scene: str = "interview_invitation",
        variables_schema: dict | None = None,
        is_default: bool = False,
        remark: str | None = None,
        created_by: str | None = None,
    ) -> EmailTemplate:
        existing = self._session.execute(
            select(EmailTemplate).where(EmailTemplate.template_code == template_code)
        ).scalar_one_or_none()
        if existing is not None:
            raise InvalidStateError(f"Email template code '{template_code}' already exists")
        if is_default:
            self._clear_default(scene)
        entity = EmailTemplate(
            template_code=template_code,
            template_name=template_name,
            subject_template=subject_template,
            html_template=html_template,
            text_template=text_template,
            scene=scene,
            variables_schema=variables_schema,
            is_default=is_default,
            remark=remark,
            created_by=created_by,
            updated_by=created_by,
        )
        self._session.add(entity)
        self._session.flush()
        return entity

    def update(
        self,
        template_code: str,
        *,
        template_name: str | None = None,
        subject_template: str | None = None,
        html_template: str | None = None,
        text_template: str | None = None,
        variables_schema: dict | None = None,
        status: str | None = None,
        is_default: bool | None = None,
        remark: str | None = None,
        updated_by: str | None = None,
    ) -> EmailTemplate:
        entity = self.get_by_code(template_code)
        if template_name is not None:
            entity.template_name = template_name
        if subject_template is not None:
            entity.subject_template = subject_template
        if html_template is not None:
            entity.html_template = html_template
        if text_template is not None:
            entity.text_template = text_template
        if variables_schema is not None:
            entity.variables_schema = variables_schema
        if status is not None:
            entity.status = status
        if remark is not None:
            entity.remark = remark
        if is_default is True:
            self._clear_default(entity.scene)
            entity.is_default = True
        elif is_default is False:
            entity.is_default = False
        if updated_by is not None:
            entity.updated_by = updated_by
        self._session.flush()
        return entity

    def _clear_default(self, scene: str) -> None:
        entities = self._session.execute(
            select(EmailTemplate).where(
                EmailTemplate.scene == scene,
                EmailTemplate.is_default.is_(True),
            )
        ).scalars()
        for entity in entities:
            entity.is_default = False
