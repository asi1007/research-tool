from src.domain.entities.product_size import ProductSize
from src.infrastructure.shipping_calculator import InternationalShippingCalculator


class TestInternationalShippingCalculator:
    def test_容積重量が実重量を上回る場合は容積重量で計算する(self) -> None:
        calculator = InternationalShippingCalculator(rate_per_kg_cny=7.0, cny_to_jpy_rate=21.0)

        size = ProductSize(length_mm=200, width_mm=100, height_mm=30)
        actual = calculator.calculate(size, weight_grams=100)

        assert actual == 18

    def test_実重量が容積重量を上回る場合は実重量で計算する(self) -> None:
        calculator = InternationalShippingCalculator(rate_per_kg_cny=7.0, cny_to_jpy_rate=21.0)

        size = ProductSize(length_mm=50, width_mm=50, height_mm=50)
        actual = calculator.calculate(size, weight_grams=2000)

        assert actual == 294

    def test_寸法も重量も無い場合は0を返す(self) -> None:
        calculator = InternationalShippingCalculator(rate_per_kg_cny=7.0, cny_to_jpy_rate=21.0)

        assert calculator.calculate(ProductSize(0, 0, 0), weight_grams=0) == 0

    def test_寸法が欠けていても実重量から計算する(self) -> None:
        calculator = InternationalShippingCalculator(rate_per_kg_cny=7.0, cny_to_jpy_rate=21.0)

        assert calculator.calculate(ProductSize(0, 0, 0), weight_grams=1000) == 147
