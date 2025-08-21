from django.apps import AppConfig


class PricingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pricing"

    def ready(self):
        import pricing.signals  # signals.py 내 시그널 핸들러 자동 등록
