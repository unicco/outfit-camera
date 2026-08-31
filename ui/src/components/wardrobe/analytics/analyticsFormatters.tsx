import { Sun, CloudRain, Snowflake, Flower2 } from 'lucide-react';

export const getSeasonIcon = (season: string) => {
  switch (season.toLowerCase()) {
    case 'spring':
      return <Flower2 className="h-4 w-4" />;
    case 'summer':
      return <Sun className="h-4 w-4" />;
    case 'autumn':
      return <CloudRain className="h-4 w-4" />;
    case 'winter':
      return <Snowflake className="h-4 w-4" />;
    default:
      return null;
  }
};
