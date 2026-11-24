import type { Factor, Lifestyle } from './healthApi'

export type Levels = Record<Factor, number>

export const referenceLevels: Readonly<Levels> = { diet: 50, exercise: 50, sleep: 50, smoking: 50 }

export const levelControls = {
  diet: {
    goal: '盐摄入程度', ends: ['较少', '较多'], scenarios: ['reduced', 'high'],
    descriptions: ['盐摄入较少', '盐摄入偏少', '盐摄入中等', '盐摄入偏多', '盐摄入较多'],
  },
  exercise: {
    goal: '日常活动程度', ends: ['较少', '较多'], scenarios: ['inactive', 'regular'],
    descriptions: ['活动较少', '活动偏少', '活动程度中等', '活动偏多', '活动较多'],
  },
  sleep: {
    goal: '作息规律程度', ends: ['不规律', '规律'], scenarios: ['irregular', 'regular'],
    descriptions: ['作息不规律', '作息偏不规律', '规律程度中等', '作息偏规律', '作息规律'],
  },
  smoking: {
    goal: '吸烟程度', ends: ['不吸烟', '较高'], scenarios: ['none', 'current'],
    descriptions: ['吸烟程度较低', '吸烟程度偏低', '吸烟程度中等', '吸烟程度偏高', '吸烟程度较高'],
  },
} as const satisfies Record<Factor, {
  goal: string
  ends: readonly [string, string]
  scenarios: readonly [string, string]
  descriptions: readonly [string, string, string, string, string]
}>

export const lifestyleFactors = Object.keys(levelControls) as Factor[]

export function describeLevel(factor: Factor, level: number) {
  if (factor === 'smoking' && level === 0) return '不吸烟'
  return levelControls[factor].descriptions[Math.max(0, Math.ceil(level / 20) - 1)]
}

export function mapLevels(levels: Levels): Lifestyle {
  const scenario: Lifestyle = {}
  for (const factor of lifestyleFactors) {
    const value = levels[factor]
    if (value === 50) continue
    const high = factor === 'smoking' ? value > 0 : value > 50
    scenario[factor] = levelControls[factor].scenarios[high ? 1 : 0]
  }
  return scenario
}

export function restoreLevels(scenario: Lifestyle, saved?: Partial<Levels>): Levels {
  const levels = { ...referenceLevels }
  for (const factor of lifestyleFactors) {
    const value = saved?.[factor]
    if (typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 100) {
      levels[factor] = value
    } else {
      const [low, high] = levelControls[factor].scenarios
      if (scenario[factor] === low) levels[factor] = 0
      if (scenario[factor] === high) levels[factor] = 100
    }
  }
  return levels
}
