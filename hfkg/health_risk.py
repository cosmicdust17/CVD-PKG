"""WHO 2019 laboratory risk estimate using the published PyCVDRisk API."""
import math
from importlib.metadata import version

from pydantic import BaseModel, ConfigDict, Field, StrictBool
from typing import Literal

MODEL = "WHO 2019（东亚实验室版）"
CITATION = "https://doi.org/10.1016/S2214-109X(19)30318-3"


class RiskInput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    model: Literal["who2019_east_asia"] = "who2019_east_asia"
    region: Literal["china_mainland"]
    age: int = Field(ge=40, le=79)
    sex: Literal["male", "female"]
    sbp: float = Field(ge=70, le=250, allow_inf_nan=False)
    total_chol: float = Field(ge=2, le=15, allow_inf_nan=False)
    smoker: StrictBool
    diabetes: StrictBool
    prior_cvd: StrictBool


def estimate(inputs):
    if inputs.prior_cvd:
        raise ValueError("已有心血管病史超出 WHO 2019 一级预防模型的适用范围。")
    from cvd_risk import who2019

    probability = float(who2019(age=inputs.age, sex=inputs.sex, sbp=inputs.sbp, smoker=inputs.smoker,
                                total_chol=inputs.total_chol, diabetes=inputs.diabetes,
                                region="east_asia", version="lab", recalibration="region"))
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("模型没有返回有效结果，请核对指标、单位和适用条件。")
    return dict(model=MODEL, model_year=2019, package_version=version("cvd-risk"),
                region="WHO 东亚地区校准（本应用限中国大陆）",
                population="40–79 岁、无既往心血管病的成人；一级预防",
                input=inputs.model_dump(), result_percent=round(100 * probability, 1), unit="%",
                horizon_years=10, outcome="10 年内首次心肌梗死或脑卒中（致死或非致死）的估计风险",
                limitations=["地区校准模型对个体及不同地区人群可能存在误差。中国队列研究曾发现校准偏差。",
                             "健康科普用途。此结果不用于确诊、用药决策或量化生活方式调整效果。",
                             "收缩压使用 mmHg，总胆固醇使用 mmol/L；录入范围是应用的输入校验。"],
                citation=CITATION, license="MIT（所调用的 WHO 2019 模块）")
