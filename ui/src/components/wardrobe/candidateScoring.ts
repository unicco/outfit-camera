export interface WardrobeMatchCandidate {
  itemId?: string;
  wardrobeItemId?: string;
  similarityScore?: number;
  matchScore?: number;
  matchReason?: string;
  name?: string;
  brand?: string;
  subcategory?: string;
  imageUrl?: string;
}

export const getCandidateId = (candidate: WardrobeMatchCandidate): string => {
  return candidate.itemId || candidate.wardrobeItemId || '';
};

export const getCandidateScore = (candidate: WardrobeMatchCandidate): number => {
  if (typeof candidate.similarityScore === 'number') {
    return candidate.similarityScore;
  }
  if (typeof candidate.matchScore === 'number') {
    return candidate.matchScore;
  }
  return 0;
};

export const rankCandidates = (
  candidates: WardrobeMatchCandidate[] | undefined | null,
  limit = 5,
): WardrobeMatchCandidate[] => {
  return (candidates || []).slice(0, limit);
};
