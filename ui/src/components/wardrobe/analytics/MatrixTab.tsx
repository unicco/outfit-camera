import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { TabsContent } from '@/components/ui/tabs';
import { formatCategory, formatSeason } from './analyticsTransforms';
import { getSeasonIcon } from './analyticsFormatters';
import type { CategorySeasonMatrix } from './types';

interface MatrixTabProps {
  categorySeasonMatrix: CategorySeasonMatrix | null;
}

export function MatrixTab({ categorySeasonMatrix }: MatrixTabProps) {
  return (
    <TabsContent value="matrix" className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>カテゴリ × 季節</CardTitle>
          <CardDescription>
            各カテゴリの季節別の服数を表示
          </CardDescription>
        </CardHeader>
        <CardContent>
          {categorySeasonMatrix && (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="text-left p-3 font-semibold whitespace-nowrap">カテゴリ</th>
                    {(categorySeasonMatrix?.seasons || []).map(season => (
                      <th key={season} className="text-center p-3 font-semibold whitespace-nowrap">
                        <div className="flex items-center justify-center gap-1">
                          {getSeasonIcon(season)}
                          {formatSeason(season)}
                        </div>
                      </th>
                    ))}
                    <th className="text-center p-3 font-semibold whitespace-nowrap">合計</th>
                  </tr>
                </thead>
                <tbody>
                  {(categorySeasonMatrix?.matrix || []).map(row => (
                    <tr key={row.category} className="border-b border-gray-200 hover:bg-gray-50">
                      <td className="p-3 font-medium whitespace-nowrap">
                        {formatCategory(row.category)}
                      </td>
                      {(categorySeasonMatrix?.seasons || []).map(season => (
                        <td key={season} className="text-center p-3 whitespace-nowrap">
                          {row.seasons[season as keyof typeof row.seasons] > 0 ? (
                            <span className="inline-flex items-center justify-center w-10 h-10 rounded-full bg-blue-100 text-blue-800 font-semibold">
                              {row.seasons[season as keyof typeof row.seasons]}
                            </span>
                          ) : (
                            <span className="text-gray-300">0</span>
                          )}
                        </td>
                      ))}
                      <td className="text-center p-3 whitespace-nowrap">
                        <span className="font-semibold">
                          {row.total}
                        </span>
                      </td>
                    </tr>
                  ))}
                  <tr className="border-t-2 border-gray-300 font-semibold bg-gray-50">
                    <td className="p-3 whitespace-nowrap">合計</td>
                    {(categorySeasonMatrix?.seasons || []).map(season => (
                      <td key={season} className="text-center p-3 whitespace-nowrap">
                        {categorySeasonMatrix.seasonTotals[season as keyof typeof categorySeasonMatrix.seasonTotals]}
                      </td>
                    ))}
                    <td className="text-center p-3 text-blue-600 whitespace-nowrap">
                      {categorySeasonMatrix.totalItems}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </TabsContent>
  );
}
