from django.db import models
import numpy as np


class MenuPricingParam(models.Model):
    menu = models.OneToOneField(
        "stores.StoreMenu", on_delete=models.CASCADE, related_name="pricing_param"
    )
    alpha = models.FloatField(default=0.0)  # 가격 민감도
    beta0 = models.FloatField(default=0.0)  # 상수항
    gamma_tilde = models.FloatField(default=0.0)  # 감마 내부 값, softplus 적용

    last_updated = models.DateTimeField(auto_now=True)

    @property
    def gamma(self):
        return -np.log(1 + np.exp(self.gamma_tilde))

    def __str__(self):
        return f"{self.menu.menu_name} Pricing Params"


class GlobalPricingParam(models.Model):
    beta0 = models.FloatField(default=0.0)
    alpha = models.FloatField(default=0.0)
    gamma_tilde = models.FloatField(default=0.0)
    updated_at = models.DateTimeField(auto_now=True)
