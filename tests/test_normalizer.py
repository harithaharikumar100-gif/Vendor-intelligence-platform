"""Tests for normalizer.py (SK-VDD-001 Section 4.2 input normalisation)."""
import pytest

from normalizer import normalize_vendor_name, validate_business_number, extract_domain


class TestNormalizeVendorName:
    def test_strips_legal_suffix(self):
        result = normalize_vendor_name("Shopify Inc.")
        assert result["normalized_name"] == "Shopify"

    def test_strips_multiple_suffix_styles(self):
        assert normalize_vendor_name("BlackBerry Limited")["normalized_name"] == "BlackBerry"
        assert normalize_vendor_name("CGI Group Inc.")["normalized_name"] == "CGI Group"

    def test_no_suffix_unchanged(self):
        # Single word, not in KNOWN_ACRONYMS, and the multi-word acronym
        # generator only fires on 2+ words -- so nothing but the raw name
        # is expected back.
        result = normalize_vendor_name("Northbridge")
        assert result["normalized_name"] == "Northbridge"
        assert result["variants"] == ["Northbridge"]

    def test_known_acronym_expansion(self):
        result = normalize_vendor_name("RBC")
        assert "Royal Bank of Canada" in result["variants"]

    def test_reverse_acronym_lookup(self):
        result = normalize_vendor_name("Royal Bank of Canada")
        assert "RBC" in result["variants"]

    def test_generates_acronym_from_multiword_name(self):
        result = normalize_vendor_name("Canadian National Railway")
        # Known acronym mapping takes priority, but the multi-word acronym
        # generator should also fire for names not in KNOWN_ACRONYMS.
        result2 = normalize_vendor_name("Northern Digital Systems")
        assert "NDS" in result2["variants"]

    def test_empty_input(self):
        result = normalize_vendor_name("")
        assert result == {"raw": "", "clean": "", "variants": []}

    def test_variants_are_deduplicated(self):
        result = normalize_vendor_name("Shopify Inc.")
        assert len(result["variants"]) == len(set(result["variants"]))

    def test_bilingual_french_variant_for_known_entity(self):
        result = normalize_vendor_name("Royal Bank of Canada")
        assert result["french_variant"] == "Banque Royale du Canada"
        assert "Banque Royale du Canada" in result["variants"]

    def test_bilingual_french_variant_via_acronym(self):
        result = normalize_vendor_name("RBC")
        assert result["french_variant"] == "Banque Royale du Canada"

    def test_no_french_variant_for_non_bilingual_entity(self):
        result = normalize_vendor_name("Shopify Inc.")
        assert result["french_variant"] is None


class TestValidateBusinessNumber:
    @pytest.mark.parametrize("bn,expected", [
        ("123456789", True),
        ("123-456-789", True),
        ("12345678", False),   # 8 digits, too short
        ("1234567890", False),  # 10 digits, too long
        ("", False),
        (None, False),
    ])
    def test_bn_length_validation(self, bn, expected):
        assert validate_business_number(bn) is expected


class TestExtractDomain:
    @pytest.mark.parametrize("url,expected", [
        ("https://www.shopify.com", "shopify.com"),
        ("http://blackberry.com/about", "blackberry.com"),
        ("www.rbc.com", "rbc.com"),
        ("", ""),
    ])
    def test_domain_extraction(self, url, expected):
        assert extract_domain(url) == expected
