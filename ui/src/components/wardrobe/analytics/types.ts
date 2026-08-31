export interface WardrobeRankingItem {
  id: string;
  name: string;
  category: string | null;
  subcategory: string | null;
  brand: string | null;
  purchasePrice: number | null;
  defaultUsageCount?: number;
  usageCount?: number;
  totalWearCount?: number;
  purchaseDate: string | null;
  lastUsedDate: string | null;
  imageUrls?: string[] | Record<string, string> | null;
  colorsPalette: {
    palette?: Array<{
      hex: string;
      rgb?: { r: number; g: number; b: number } | number[];
      position?: number;
      percentage?: number;
      dominant?: boolean;
    }>;
    primary?: {
      hex: string;
      rgb?: number[];
      percentage?: number;
      dominant?: boolean;
    };
    secondary?: {
      hex: string;
      rgb?: number[];
      percentage?: number;
      dominant?: boolean;
    };
    accent?: {
      hex: string;
      rgb?: number[];
      percentage?: number;
      dominant?: boolean;
    };
  } | null;
  costPerWear?: number | null;
}

export interface WardrobeRankings {
  mostWorn: WardrobeRankingItem[];
  leastWorn: WardrobeRankingItem[];
  mostExpensive: WardrobeRankingItem[];
  bestCostPerformance: WardrobeRankingItem[];
}

export interface CategorySeasonMatrix {
  matrix: Array<{
    category: string;
    seasons: {
      Spring: number;
      Summer: number;
      Autumn: number;
      Winter: number;
    };
    total: number;
  }>;
  seasonTotals: {
    Spring: number;
    Summer: number;
    Autumn: number;
    Winter: number;
  };
  categories: string[];
  seasons: string[];
  totalItems: number;
}

export interface WardrobeAnalyticsData {
  overview: {
    totalItems: number;
    activeItems: number;
    storedItems: number;
    totalValue: number;
    totalWears: number;
    averageCostPerWear: number;
    averageWearsPerItem: number;
    mostWornItem: {
      id: string;
      name: string;
      wearCount: number;
    };
    leastWornItem: {
      id: string;
      name: string;
      wearCount: number;
    };
  };
  categoryBreakdown: Array<{
    category: string;
    count: number;
    value: number;
    wearCount: number;
    costPerWear: number;
    percentage: number;
  }>;
  wearFrequency: Array<{
    month: string;
    wearCount: number;
  }>;
  costAnalysis: {
    byCategory: Array<{
      category: string;
      totalCost: number;
      averageCost: number;
      costPerWear: number;
    }>;
    byBrand: Array<{
      brand: string;
      totalCost: number;
      itemCount: number;
      averageCost: number;
    }>;
  };
  seasonalUsage: Array<{
    season: string;
    itemCount: number;
    wearCount: number;
    utilizationRate: number;
  }>;
  brandDistribution: Array<{
    brand: string;
    count: number;
    percentage: number;
  }>;
  purchaseTimeline: Array<{
    month: string;
    count: number;
    value: number;
  }>;
}
