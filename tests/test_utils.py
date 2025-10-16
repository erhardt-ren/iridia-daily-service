"""Tests for utility functions."""

import pytest


class TestCategoryDetection:
    """Test category detection and classification."""
    
    @pytest.mark.parametrize("text,expected_category", [
        ("Research on brain activity and neural pathways", "NEUROSCIENCE"),
        ("Discovery of new galaxy in deep space", "SPACE"),
        ("CRISPR gene editing breakthrough", "BIOLOGY"),
        ("Climate change impacts on ecosystems", "ENVIRONMENT"),
        ("Quantum physics experiments reveal new particles", "PHYSICS"),
        ("New drug treatment for cancer patients", "MEDICINE"),
        ("Machine learning algorithm improves predictions", "TECHNOLOGY"),
        ("Abstract mathematical topology study", "RESEARCH"),  # default - no matching keywords
    ])
    def test_category_detection(self, text, expected_category):
        """Test that text is correctly categorized."""
        from iridia_daily.utils import get_category_info
        
        color, label = get_category_info(text)
        
        assert expected_category in label
        assert color.startswith('#')
        assert len(color) == 7  # Hex color format
    
    def test_category_returns_valid_color_and_label(self):
        """Test that category info always returns valid format."""
        from iridia_daily.utils import get_category_info
        
        color, label = get_category_info("Random text that doesn't match anything")
        
        # Should still return valid color and label
        assert isinstance(color, str)
        assert isinstance(label, str)
        assert color.startswith('#')
        assert len(label) > 0