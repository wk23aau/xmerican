"""
xCLICK ROI (Region of Interest) Masking
Filters out irrelevant areas like ads, sidebars, and noise
Implements "negative space understanding" from ChatGPT recommendations
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Set
from enum import Enum


class RegionType(Enum):
    """Types of regions for filtering"""
    INCLUDE = "include"  # Focus on this area
    EXCLUDE = "exclude"  # Ignore this area
    AD = "ad"            # Likely advertisement
    SIDEBAR = "sidebar"  # Sidebar content
    HEADER = "header"    # Header/nav area
    FOOTER = "footer"    # Footer area


@dataclass
class Region:
    """A rectangular region with a type"""
    x1: float
    y1: float
    x2: float
    y2: float
    region_type: RegionType
    confidence: float = 1.0
    label: str = ""
    
    @property
    def width(self) -> float:
        return self.x2 - self.x1
    
    @property
    def height(self) -> float:
        return self.y2 - self.y1
    
    @property
    def area(self) -> float:
        return self.width * self.height
    
    @property
    def center(self) -> Tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)
    
    def contains_point(self, x: float, y: float) -> bool:
        """Check if point is inside region"""
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2
    
    def overlaps(self, other: 'Region') -> bool:
        """Check if regions overlap"""
        return not (self.x2 < other.x1 or other.x2 < self.x1 or
                    self.y2 < other.y1 or other.y2 < self.y1)
    
    def iou(self, other: 'Region') -> float:
        """Compute Intersection over Union"""
        x1 = max(self.x1, other.x1)
        y1 = max(self.y1, other.y1)
        x2 = min(self.x2, other.x2)
        y2 = min(self.y2, other.y2)
        
        if x2 <= x1 or y2 <= y1:
            return 0.0
        
        intersection = (x2 - x1) * (y2 - y1)
        union = self.area + other.area - intersection
        return intersection / union if union > 0 else 0.0


# Common ad-related keywords for detection
AD_KEYWORDS = {
    "ad", "ads", "advertisement", "sponsor", "sponsored",
    "promoted", "promo", "banner", "adsense", "advert",
    "commercial", "marketing", "affiliate"
}

# Common ad-related class/id patterns
AD_PATTERNS = [
    "ad-", "ads-", "advert", "sponsor", "promo",
    "banner", "sidebar-ad", "google_ads", "adsense",
    "dfp-", "gpt-ad", "outbrain", "taboola"
]


@dataclass
class ROIMask:
    """
    Manages regions of interest for filtering detected elements.
    Implements negative space understanding.
    """
    viewport_width: int = 1280
    viewport_height: int = 720
    
    # Regions
    include_regions: List[Region] = field(default_factory=list)
    exclude_regions: List[Region] = field(default_factory=list)
    
    # Auto-detected regions
    detected_ads: List[Region] = field(default_factory=list)
    
    # Settings
    auto_detect_ads: bool = True
    exclude_edges_px: int = 50  # Ignore elements near viewport edges
    
    def add_include_region(self, x1: float, y1: float, x2: float, y2: float, label: str = ""):
        """Add a region to focus on"""
        self.include_regions.append(Region(x1, y1, x2, y2, RegionType.INCLUDE, label=label))
    
    def add_exclude_region(self, x1: float, y1: float, x2: float, y2: float, 
                           region_type: RegionType = RegionType.EXCLUDE, label: str = ""):
        """Add a region to ignore"""
        self.exclude_regions.append(Region(x1, y1, x2, y2, region_type, label=label))
    
    def add_standard_exclusions(self):
        """Add common exclusion zones (edges, corners)"""
        w, h = self.viewport_width, self.viewport_height
        edge = self.exclude_edges_px
        
        # Top edge (often ads/banners)
        self.add_exclude_region(0, 0, w, edge, RegionType.HEADER, "top_edge")
        
        # Bottom edge (often cookie banners)
        self.add_exclude_region(0, h - edge, w, h, RegionType.FOOTER, "bottom_edge")
        
        # Right sidebar (often ads)
        self.add_exclude_region(w - 200, edge, w, h - edge, RegionType.SIDEBAR, "right_sidebar")
    
    def detect_ad_from_element(self, element: dict) -> bool:
        """
        Check if an element is likely an ad based on its attributes.
        Returns True if element should be excluded as an ad.
        """
        # Check label/text
        label = element.get("label", "").lower()
        for keyword in AD_KEYWORDS:
            if keyword in label:
                return True
        
        # Check DOM ID
        dom_id = element.get("dom_id", "").lower()
        for pattern in AD_PATTERNS:
            if pattern in dom_id:
                return True
        
        # Check tag/class (if available)
        tag = element.get("tag", "").lower()
        if tag in ("ad", "aside", "ins"):  # Common ad container tags
            return True
        
        return False
    
    def is_in_focus(self, x: float, y: float) -> bool:
        """
        Check if a point is in the focus area.
        Returns True if point should be considered.
        """
        # If we have include regions, point must be in at least one
        if self.include_regions:
            in_include = any(r.contains_point(x, y) for r in self.include_regions)
            if not in_include:
                return False
        
        # Check exclude regions
        for region in self.exclude_regions + self.detected_ads:
            if region.contains_point(x, y):
                return False
        
        return True
    
    def is_element_valid(self, element: dict) -> bool:
        """
        Check if an element should be considered based on ROI.
        Full validation including position and ad detection.
        """
        # Get center point
        bbox = element.get("bbox", [0, 0, 0, 0])
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        
        # Check position
        if not self.is_in_focus(cx, cy):
            return False
        
        # Check for ads
        if self.auto_detect_ads and self.detect_ad_from_element(element):
            # Add to detected ads list
            self.detected_ads.append(Region(
                bbox[0], bbox[1], bbox[2], bbox[3],
                RegionType.AD,
                label=element.get("label", "")[:20]
            ))
            return False
        
        return True
    
    def filter_elements(self, elements: List[dict]) -> List[dict]:
        """
        Filter a list of elements, keeping only those in focus areas.
        """
        return [e for e in elements if self.is_element_valid(e)]
    
    def get_focus_summary(self) -> str:
        """Get summary of current focus areas"""
        parts = []
        if self.include_regions:
            parts.append(f"{len(self.include_regions)} include zones")
        if self.exclude_regions:
            parts.append(f"{len(self.exclude_regions)} exclude zones")
        if self.detected_ads:
            parts.append(f"{len(self.detected_ads)} ads detected")
        return ", ".join(parts) if parts else "no filters"
    
    def clear(self):
        """Clear all regions"""
        self.include_regions.clear()
        self.exclude_regions.clear()
        self.detected_ads.clear()
    
    def set_focus_area(self, x1: float, y1: float, x2: float, y2: float):
        """Set a single focus area (common use case)"""
        self.include_regions.clear()
        self.add_include_region(x1, y1, x2, y2, "focus")
    
    def focus_center(self, margin_pct: float = 20):
        """Focus on center of viewport, excluding edges"""
        margin_x = self.viewport_width * margin_pct / 100
        margin_y = self.viewport_height * margin_pct / 100
        self.set_focus_area(margin_x, margin_y, 
                           self.viewport_width - margin_x, 
                           self.viewport_height - margin_y)


# Singleton instance
_roi_mask: Optional[ROIMask] = None

def get_roi_mask() -> ROIMask:
    """Get or create the global ROI mask"""
    global _roi_mask
    if _roi_mask is None:
        _roi_mask = ROIMask()
    return _roi_mask

def reset_roi_mask():
    """Reset global ROI mask"""
    global _roi_mask
    _roi_mask = ROIMask()
