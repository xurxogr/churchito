"""Tests para VerificationService."""

from sqlalchemy.ext.asyncio import AsyncSession

from discord_bot.verification.enums import VerificationStatus, VerificationType
from discord_bot.verification.service import VerificationService


class TestVerificationService:
    """Tests para VerificationService."""

    async def test_create_request(self, test_session: AsyncSession) -> None:
        """Probar creacion de solicitud."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        assert request.id is not None
        assert request.guild_id == 123
        assert request.user_id == 456
        assert request.username == "TestUser"
        assert request.verification_type == VerificationType.REGULAR
        assert request.status == VerificationStatus.PENDING_SCREENSHOTS

    async def test_create_request_ally(self, test_session: AsyncSession) -> None:
        """Probar creacion de solicitud de aliado."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.ALLY,
        )

        assert request.verification_type == VerificationType.ALLY

    async def test_get_request(self, test_session: AsyncSession) -> None:
        """Probar obtencion de solicitud por ID."""
        service = VerificationService(test_session)

        created = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        retrieved = await service.get_request(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.username == "TestUser"

    async def test_get_request_not_found(self, test_session: AsyncSession) -> None:
        """Probar obtencion de solicitud inexistente."""
        service = VerificationService(test_session)
        result = await service.get_request(99999)
        assert result is None

    async def test_get_pending_by_user(self, test_session: AsyncSession) -> None:
        """Probar obtencion de solicitud pendiente por usuario."""
        service = VerificationService(test_session)

        await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        pending = await service.get_pending_by_user(guild_id=123, user_id=456)
        assert pending is not None
        assert pending.user_id == 456

    async def test_get_pending_by_user_no_pending(self, test_session: AsyncSession) -> None:
        """Probar obtencion de solicitud pendiente cuando no hay ninguna."""
        service = VerificationService(test_session)
        pending = await service.get_pending_by_user(guild_id=123, user_id=456)
        assert pending is None

    async def test_get_pending_by_user_ignores_completed(self, test_session: AsyncSession) -> None:
        """Probar que get_pending_by_user ignora solicitudes completadas."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.approve(request_id=request.id, reviewer_id=789, reviewer_username="Mod")

        pending = await service.get_pending_by_user(guild_id=123, user_id=456)
        assert pending is None

    async def test_get_any_pending_by_user(self, test_session: AsyncSession) -> None:
        """Probar obtencion de cualquier solicitud pendiente de un usuario."""
        service = VerificationService(test_session)

        # Crear solicitud en un guild
        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        # Buscar sin especificar guild
        pending = await service.get_any_pending_by_user(456)
        assert pending is not None
        assert pending.id == request.id
        assert pending.guild_id == 123

    async def test_get_any_pending_by_user_no_pending(self, test_session: AsyncSession) -> None:
        """Probar get_any_pending_by_user cuando no hay solicitudes pendientes."""
        service = VerificationService(test_session)
        pending = await service.get_any_pending_by_user(456)
        assert pending is None

    async def test_get_any_pending_by_user_ignores_pending_review(
        self, test_session: AsyncSession
    ) -> None:
        """Probar que get_any_pending_by_user solo devuelve PENDING_SCREENSHOTS."""
        service = VerificationService(test_session)

        # Crear solicitud y actualizar a PENDING_REVIEW
        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.update_screenshots(
            request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
        )

        # No debe encontrar porque ya tiene capturas (PENDING_REVIEW)
        pending = await service.get_any_pending_by_user(456)
        assert pending is None

    async def test_get_any_pending_by_user_returns_most_recent(
        self, test_session: AsyncSession
    ) -> None:
        """Probar que get_any_pending_by_user devuelve la mas reciente."""
        service = VerificationService(test_session)

        # Crear solicitud en guild 111
        await service.create_request(
            guild_id=111,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        # Crear solicitud en guild 222 (mas reciente)
        request2 = await service.create_request(
            guild_id=222,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.ALLY,
        )

        pending = await service.get_any_pending_by_user(456)
        assert pending is not None
        assert pending.id == request2.id
        assert pending.guild_id == 222

    async def test_get_all_pending_screenshots(self, test_session: AsyncSession) -> None:
        """Probar obtencion de todas las solicitudes esperando capturas."""
        service = VerificationService(test_session)

        # Crear varias solicitudes
        await service.create_request(
            guild_id=111,
            user_id=456,
            username="User1",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.create_request(
            guild_id=222,
            user_id=789,
            username="User2",
            guild_name="Test Guild",
            verification_type=VerificationType.ALLY,
        )

        pending = await service.get_all_pending_screenshots()
        assert len(pending) == 2

    async def test_get_all_pending_screenshots_empty(self, test_session: AsyncSession) -> None:
        """Probar get_all_pending_screenshots cuando no hay solicitudes."""
        service = VerificationService(test_session)
        pending = await service.get_all_pending_screenshots()
        assert pending == []

    async def test_get_all_pending_screenshots_ignores_other_statuses(
        self, test_session: AsyncSession
    ) -> None:
        """Probar que get_all_pending_screenshots ignora otros estados."""
        service = VerificationService(test_session)

        # Crear solicitud y aprobarla
        request1 = await service.create_request(
            guild_id=111,
            user_id=456,
            username="User1",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.approve(request_id=request1.id, reviewer_id=999, reviewer_username="Mod")

        # Crear solicitud y actualizarla a PENDING_REVIEW
        request2 = await service.create_request(
            guild_id=222,
            user_id=789,
            username="User2",
            guild_name="Test Guild",
            verification_type=VerificationType.ALLY,
        )
        await service.update_screenshots(
            request_id=request2.id, url1="url1", url2="url2", guild_name="Test Guild"
        )

        # Crear solicitud pendiente de capturas
        await service.create_request(
            guild_id=333,
            user_id=101,
            username="User3",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        pending = await service.get_all_pending_screenshots()
        assert len(pending) == 1
        assert pending[0].user_id == 101

    async def test_get_user_history(self, test_session: AsyncSession) -> None:
        """Probar obtencion de historial de usuario."""
        service = VerificationService(test_session)

        request1 = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.approve(request_id=request1.id, reviewer_id=789, reviewer_username="Mod")

        await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.ALLY,
        )

        history = await service.get_user_history(guild_id=123, user_id=456)
        assert len(history) == 2
        assert history[0].verification_type == VerificationType.ALLY
        assert history[1].verification_type == VerificationType.REGULAR

    async def test_get_user_history_empty(self, test_session: AsyncSession) -> None:
        """Probar historial vacio."""
        service = VerificationService(test_session)
        history = await service.get_user_history(guild_id=123, user_id=456)
        assert history == []

    async def test_update_screenshots(self, test_session: AsyncSession) -> None:
        """Probar actualizacion de capturas."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        updated = await service.update_screenshots(
            request.id,
            "http://example.com/1.png",
            "http://example.com/2.png",
            "Test Guild",
        )

        assert updated is not None
        assert updated.screenshot_1_url == "http://example.com/1.png"
        assert updated.screenshot_2_url == "http://example.com/2.png"
        assert updated.status == VerificationStatus.PENDING_REVIEW
        assert updated.screenshots_submitted_at is not None

    async def test_update_screenshots_not_found(self, test_session: AsyncSession) -> None:
        """Probar actualizacion de capturas para solicitud inexistente."""
        service = VerificationService(test_session)
        result = await service.update_screenshots(
            request_id=99999, url1="url1", url2="url2", guild_name="Test Guild"
        )
        assert result is None

    async def test_set_mod_message_id(self, test_session: AsyncSession) -> None:
        """Probar guardado de ID de mensaje de moderacion."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        await service.set_mod_message_id(request_id=request.id, message_id=111)

        updated = await service.get_request(request.id)
        assert updated is not None
        assert updated.mod_message_id == 111

    async def test_set_mod_message_id_not_found(self, test_session: AsyncSession) -> None:
        """Probar set_mod_message_id para solicitud inexistente."""
        service = VerificationService(test_session)
        # No deberia fallar, solo retornar sin hacer nada
        await service.set_mod_message_id(request_id=99999, message_id=111)

    async def test_approve(self, test_session: AsyncSession) -> None:
        """Probar aprobacion de solicitud."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        approved = await service.approve(
            request_id=request.id, reviewer_id=789, reviewer_username="ModUser"
        )

        assert approved is not None
        assert approved.status == VerificationStatus.APPROVED
        assert approved.reviewed_by_id == 789
        assert approved.reviewed_by_username == "ModUser"
        assert approved.reviewed_at is not None

    async def test_approve_not_found(self, test_session: AsyncSession) -> None:
        """Probar aprobacion de solicitud inexistente."""
        service = VerificationService(test_session)
        result = await service.approve(request_id=99999, reviewer_id=789, reviewer_username="Mod")
        assert result is None

    async def test_reject(self, test_session: AsyncSession) -> None:
        """Probar rechazo de solicitud."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        rejected = await service.reject(
            request_id=request.id,
            reviewer_id=789,
            reviewer_username="ModUser",
            reason="Capturas invalidas",
        )

        assert rejected is not None
        assert rejected.status == VerificationStatus.REJECTED
        assert rejected.reviewed_by_id == 789
        assert rejected.reviewed_by_username == "ModUser"
        assert rejected.rejection_reason == "Capturas invalidas"
        assert rejected.reviewed_at is not None

    async def test_reject_not_found(self, test_session: AsyncSession) -> None:
        """Probar rechazo de solicitud inexistente."""
        service = VerificationService(test_session)
        result = await service.reject(
            request_id=99999, reviewer_id=789, reviewer_username="Mod", reason="reason"
        )
        assert result is None

    async def test_cancel(self, test_session: AsyncSession) -> None:
        """Probar cancelacion de solicitud."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        cancelled = await service.cancel(request.id)

        assert cancelled is not None
        assert cancelled.status == VerificationStatus.CANCELLED

    async def test_cancel_not_found(self, test_session: AsyncSession) -> None:
        """Probar cancelacion de solicitud inexistente."""
        service = VerificationService(test_session)
        result = await service.cancel(99999)
        assert result is None

    async def test_different_guilds_isolated(self, test_session: AsyncSession) -> None:
        """Probar que diferentes guilds tienen datos aislados."""
        service = VerificationService(test_session)

        await service.create_request(
            guild_id=111,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        await service.create_request(
            guild_id=222,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.ALLY,
        )

        pending_111 = await service.get_pending_by_user(guild_id=111, user_id=456)
        pending_222 = await service.get_pending_by_user(guild_id=222, user_id=456)

        assert pending_111 is not None
        assert pending_222 is not None
        assert pending_111.verification_type == VerificationType.REGULAR
        assert pending_222.verification_type == VerificationType.ALLY

    async def test_revert_to_pending_review(self, test_session: AsyncSession) -> None:
        """Probar reversion de solicitud rechazada a pendiente de revision."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        # Rechazar primero
        await service.reject(
            request_id=request.id,
            reviewer_id=789,
            reviewer_username="Auto",
            reason="Razon automatica",
        )

        # Revertir a pendiente de revision
        reverted = await service.revert_to_pending_review(request.id)

        assert reverted is not None
        assert reverted.status == VerificationStatus.PENDING_REVIEW
        assert reverted.reviewed_by_id is None
        assert reverted.reviewed_by_username is None
        assert reverted.rejection_reason is None
        assert reverted.reviewed_at is None

    async def test_revert_to_pending_review_not_rejected(self, test_session: AsyncSession) -> None:
        """Probar que no se puede revertir solicitud que no esta rechazada."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )

        # Intentar revertir sin rechazar primero
        result = await service.revert_to_pending_review(request.id)

        assert result is None

    async def test_revert_to_pending_review_not_found(self, test_session: AsyncSession) -> None:
        """Probar reversion de solicitud inexistente."""
        service = VerificationService(test_session)
        result = await service.revert_to_pending_review(99999)
        assert result is None

    async def test_get_latest_by_user(self, test_session: AsyncSession) -> None:
        """Probar obtener ultima solicitud de un usuario."""
        service = VerificationService(test_session)

        # Crear primera solicitud
        request1 = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.cancel(request1.id)

        # Crear segunda solicitud
        request2 = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.ALLY,
        )

        latest = await service.get_latest_by_user(guild_id=123, user_id=456)

        assert latest is not None
        assert latest.id == request2.id
        assert latest.verification_type == VerificationType.ALLY

    async def test_get_latest_by_user_not_found(self, test_session: AsyncSession) -> None:
        """Probar obtener ultima solicitud de usuario sin solicitudes."""
        service = VerificationService(test_session)
        result = await service.get_latest_by_user(guild_id=123, user_id=456)
        assert result is None

    async def test_get_pending_with_mod_messages(self, test_session: AsyncSession) -> None:
        """Probar obtencion de solicitudes pendientes con mensaje de moderacion."""
        service = VerificationService(test_session)

        # Crear solicitud con mod_message_id y estado PENDING_REVIEW
        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.update_screenshots(
            request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
        )
        await service.set_mod_message_id(request_id=request.id, message_id=789)

        pending = await service.get_pending_with_mod_messages()
        assert len(pending) == 1
        assert pending[0].mod_message_id == 789

    async def test_get_pending_with_mod_messages_empty(self, test_session: AsyncSession) -> None:
        """Probar get_pending_with_mod_messages cuando no hay solicitudes."""
        service = VerificationService(test_session)
        pending = await service.get_pending_with_mod_messages()
        assert pending == []

    async def test_get_pending_with_mod_messages_ignores_without_mod_message(
        self, test_session: AsyncSession
    ) -> None:
        """Probar que ignora solicitudes sin mod_message_id."""
        service = VerificationService(test_session)

        # Crear solicitud sin mod_message_id
        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.update_screenshots(
            request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
        )
        # No establecer mod_message_id

        pending = await service.get_pending_with_mod_messages()
        assert pending == []

    async def test_get_pending_with_mod_messages_ignores_pending_screenshots(
        self, test_session: AsyncSession
    ) -> None:
        """Probar que ignora solicitudes en estado PENDING_SCREENSHOTS."""
        service = VerificationService(test_session)

        # Crear solicitud en PENDING_SCREENSHOTS con mod_message_id
        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.set_mod_message_id(request_id=request.id, message_id=789)
        # No actualizar screenshots, sigue en PENDING_SCREENSHOTS

        pending = await service.get_pending_with_mod_messages()
        assert pending == []

    async def test_get_pending_with_mod_messages_ignores_approved(
        self, test_session: AsyncSession
    ) -> None:
        """Probar que ignora solicitudes aprobadas."""
        service = VerificationService(test_session)

        request = await service.create_request(
            guild_id=123,
            user_id=456,
            username="TestUser",
            guild_name="Test Guild",
            verification_type=VerificationType.REGULAR,
        )
        await service.update_screenshots(
            request_id=request.id, url1="url1", url2="url2", guild_name="Test Guild"
        )
        await service.set_mod_message_id(request_id=request.id, message_id=789)
        await service.approve(request_id=request.id, reviewer_id=999, reviewer_username="Mod")

        pending = await service.get_pending_with_mod_messages()
        assert pending == []
