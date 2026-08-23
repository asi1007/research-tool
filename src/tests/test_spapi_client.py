from src.infrastructure.spapi_client import SpApiClient


CATALOG_RESPONSE = {
    "attributes": {
        "item_name": [{"value": "SP-API 商品名"}],
        "street_date": [{"value": "2019-03-11T08:00:01.000Z"}],
    },
    "images": [{"images": [{"link": "https://m.media-amazon.com/images/I/71abc.jpg"}]}],
    "dimensions": [
        {
            "type": "package",
            "length": {"value": 7.87, "unit": "inches"},
            "width": {"value": 3.94, "unit": "inches"},
            "height": {"value": 1.18, "unit": "inches"},
            "weight": {"value": 0.33, "unit": "pounds"},
        }
    ],
}


class TestSpApiExtractCatalog:
    def test_商品名と画像を抽出する(self) -> None:
        info = SpApiClient.extract_catalog(CATALOG_RESPONSE)

        assert info["title"] == "SP-API 商品名"
        assert info["image_url"] == "https://m.media-amazon.com/images/I/71abc.jpg"

    def test_発売日はISO8601から日付部分だけ取る(self) -> None:
        assert SpApiClient.extract_catalog(CATALOG_RESPONSE)["release_date"] == "2019-03-11"

    def test_street_dateが無ければproduct_site_launch_dateを使う(self) -> None:
        response = {
            "attributes": {"product_site_launch_date": [{"value": "2020-06-17T00:00:00.000Z"}]}
        }
        assert SpApiClient.extract_catalog(response)["release_date"] == "2020-06-17"

    def test_インチ寸法をミリメートルに換算する(self) -> None:
        size = SpApiClient.extract_catalog(CATALOG_RESPONSE)["size"]

        assert round(size.length_mm) == 200
        assert round(size.width_mm) == 100
        assert round(size.height_mm) == 30

    def test_ポンド重量をグラムに換算する(self) -> None:
        assert round(SpApiClient.extract_catalog(CATALOG_RESPONSE)["weight_grams"]) == 150

    def test_センチメートル指定はそのまま10倍する(self) -> None:
        response = {
            "dimensions": [
                {
                    "type": "package",
                    "length": {"value": 20, "unit": "centimeters"},
                    "weight": {"value": 150, "unit": "grams"},
                }
            ]
        }
        extracted = SpApiClient.extract_catalog(response)

        assert extracted["size"].length_mm == 200
        assert extracted["weight_grams"] == 150

    def test_空のレスポンスでも落ちない(self) -> None:
        extracted = SpApiClient.extract_catalog({})

        assert extracted["title"] == ""
        assert extracted["size"].is_empty


class TestSpApiExtractFees:
    def test_販売手数料とFBA手数料を抽出する(self) -> None:
        response = {
            "payload": {
                "FeesEstimateResult": {
                    "Status": "Success",
                    "FeesEstimate": {
                        "FeeDetailList": [
                            {"FeeType": "ReferralFee", "FeeAmount": {"Amount": 74}},
                            {"FeeType": "FBAFees", "FeeAmount": {"Amount": 290}},
                        ]
                    },
                }
            }
        }
        fees = SpApiClient.extract_fees(response)

        assert fees["referral_fee"] == 74
        assert fees["fba_fee"] == 290

    def test_ステータスが失敗ならゼロを返す(self) -> None:
        response = {"payload": {"FeesEstimateResult": {"Status": "ClientError"}}}
        fees = SpApiClient.extract_fees(response)

        assert fees == {"referral_fee": 0, "fba_fee": 0}

    def test_空のレスポンスならゼロを返す(self) -> None:
        assert SpApiClient.extract_fees({}) == {"referral_fee": 0, "fba_fee": 0}


class TestVariableClosingFee:
    def test_成約料をFBA手数料に加算する(self) -> None:
        response = {
            "payload": {
                "FeesEstimateResult": {
                    "Status": "Success",
                    "FeesEstimate": {
                        "FeeDetailList": [
                            {"FeeType": "ReferralFee", "FeeAmount": {"Amount": 74}},
                            {"FeeType": "FBAFees", "FeeAmount": {"Amount": 290}},
                            {"FeeType": "VariableClosingFee", "FeeAmount": {"Amount": 60}},
                        ]
                    },
                }
            }
        }
        fees = SpApiClient.extract_fees(response)

        assert fees["fba_fee"] == 350
        assert fees["referral_fee"] == 74

    def test_成約料が無ければFBA手数料のみ(self) -> None:
        response = {
            "payload": {
                "FeesEstimateResult": {
                    "Status": "Success",
                    "FeesEstimate": {
                        "FeeDetailList": [{"FeeType": "FBAFees", "FeeAmount": {"Amount": 290}}]
                    },
                }
            }
        }
        assert SpApiClient.extract_fees(response)["fba_fee"] == 290
