/** Maps URL slug → mockBiomarkers key (handles aliases like fasting-glucose → glucose). */
export const SLUG_TO_KEY: Record<string, string> = {
  'fasting-glucose': 'glucose',
  glucose: 'glucose',
  hba1c: 'hba1c',
  ldl: 'ldl',
  hdl: 'hdl',
  triglyceride: 'tg',
  tg: 'tg',
  'total-cholesterol': 'total-cholesterol',
  'vitamin-d': 'vitd',
  vitd: 'vitd',
  tsh: 'tsh',
  ft4: 'ft4',
  thyroglobulin: 'thyroglobulin',
  alt: 'alt',
  ast: 'ast',
  ggt: 'ggt',
  creatinine: 'creatinine',
  egfr: 'egfr',
  ferritin: 'ferritin',
  b12: 'b12',
  'hs-crp': 'hs-crp',
}

/** Maps backend metricType → AI Copilot biomarker URL slug. */
export const METRIC_TYPE_TO_SLUG: Record<string, string> = {
  fasting_glucose: 'fasting-glucose',
  hba1c: 'hba1c',
  triglyceride: 'triglyceride',
  hdl: 'hdl',
  ldl: 'ldl',
  total_cholesterol: 'total-cholesterol',
  tsh: 'tsh',
  ft4: 'ft4',
  thyroglobulin: 'thyroglobulin',
  creatinine: 'creatinine',
  egfr: 'egfr',
  alt: 'alt',
  ast: 'ast',
  ggt: 'ggt',
  ferritin: 'ferritin',
  vitamin_b12: 'b12',
  vitamin_d: 'vitamin-d',
  hs_crp: 'hs-crp',
}

/** Maps mockBiomarkers key → backend metric_type for live API lookup. */
export const BIOMARKER_KEY_TO_METRIC_TYPE: Record<string, string> = {
  glucose: 'fasting_glucose',
  hba1c: 'hba1c',
  tg: 'triglyceride',
  hdl: 'hdl',
  ldl: 'ldl',
  'total-cholesterol': 'total_cholesterol',
  tsh: 'tsh',
  ft4: 'ft4',
  thyroglobulin: 'thyroglobulin',
  creatinine: 'creatinine',
  egfr: 'egfr',
  alt: 'alt',
  ast: 'ast',
  ggt: 'ggt',
  ferritin: 'ferritin',
  b12: 'vitamin_b12',
  vitd: 'vitamin_d',
  'hs-crp': 'hs_crp',
}

/** Resolve a URL slug to the mockBiomarkers key, falling back to the slug itself. */
export function resolveSlug(slug: string): string {
  return SLUG_TO_KEY[slug] ?? slug
}
