from uuid import UUID

from celery import current_app as celery_app

from app.database import DbSession
from app.schemas.auth import LiveSyncMode
from app.services.providers.base_strategy import BaseProviderStrategy, ProviderCapabilities, ProviderCoverage
from app.services.providers.withings.coverage import HEALTH_SCORES, SLEEP_FIELDS, TIMESERIES, WORKOUT_FIELDS
from app.services.providers.withings.data_247 import Withings247Data
from app.services.providers.withings.notify_service import WithingsNotifyService
from app.services.providers.withings.oauth import WithingsOAuth
from app.services.providers.withings.tasks import REGISTER_USER_WEBHOOKS_TASK
from app.services.providers.withings.webhook_handler import WithingsWebhookHandler
from app.services.providers.withings.workouts import WithingsWorkouts


class WithingsStrategy(BaseProviderStrategy):
    # Narrowed from the base's optional: Withings always manages its own subscriptions.
    webhook_service: WithingsNotifyService

    def __init__(self) -> None:
        super().__init__()
        self.oauth = WithingsOAuth(
            user_repo=self.user_repo,
            connection_repo=self.connection_repo,
            provider_name=self.name,
            api_base_url=self.api_base_url,
        )
        self.data_247 = Withings247Data(
            provider_name=self.name,
            api_base_url=self.api_base_url,
            oauth=self.oauth,
        )
        self.workouts = WithingsWorkouts(
            workout_repo=self.workout_repo,
            connection_repo=self.connection_repo,
            provider_name=self.name,
            api_base_url=self.api_base_url,
            oauth=self.oauth,
        )
        self.webhooks = WithingsWebhookHandler(
            data_247=self.data_247,
            workouts=self.workouts,
            default_live_sync_mode=self.default_live_sync_mode,
        )
        self.webhook_service = WithingsNotifyService(
            connection_repo=self.connection_repo,
            oauth=self.oauth,
            default_live_sync_mode=self.default_live_sync_mode,
        )

    @property
    def name(self) -> str:
        return "withings"

    @property
    def api_base_url(self) -> str:
        return "https://wbsapi.withings.net"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            rest_pull=True,
            webhook_ping=True,
            webhook_registration_api=True,
            webhook_subscription_per_user=True,
        )

    def on_connect(self, db: DbSession, user_id: UUID) -> None:
        """Subscribe this user to notifications, once their bearer token is stored.

        Enqueued rather than run inline: subscribing is a list plus one call per
        appli, which the OAuth callback cannot wait on.
        """
        if self.effective_live_sync_mode(db) != LiveSyncMode.WEBHOOK:
            return
        celery_app.send_task(
            REGISTER_USER_WEBHOOKS_TASK,
            args=[self.name, str(user_id)],
            queue="webhook_sync",
        )

    @property
    def coverage(self) -> ProviderCoverage:
        return ProviderCoverage(
            timeseries=TIMESERIES,
            workout_fields=WORKOUT_FIELDS,
            sleep_fields=SLEEP_FIELDS,
            health_scores=HEALTH_SCORES,
        )
