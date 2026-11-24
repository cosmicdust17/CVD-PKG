import type { EdgeData, NodeData } from '@antv/g6'
import type { Entity, Relation } from '../types/graph'

const palette = [
  { fill: '#f2a862', stroke: '#a85621', text: '#49260f' },
  { fill: '#234d79', stroke: '#163659', text: '#ffffff' },
  { fill: '#75c5b5', stroke: '#347e71', text: '#143b35' },
  { fill: '#c2a8e7', stroke: '#7952a6', text: '#392252' },
]

const colors: Record<string, typeof palette[number]> = {
  '危险因素': palette[0], '心血管疾病': palette[1], '健康指标': palette[2], '人群': palette[3],
}

export function colorFor(type: string) {
  return colors[type] ?? { fill: '#a9bfd2', stroke: '#547593', text: '#1c354b' }
}

export function toNode(entity: Entity, position: [number, number], center: boolean, compact: boolean): NodeData {
  const color = colorFor(entity.entityType)
  const chars = [...entity.name]
  const limit = center ? 10 : compact ? 5 : 7
  const label = chars.length <= limit ? entity.name
    : [chars.slice(0, limit).join(''),
      chars.length > limit * 2 ? chars.slice(limit, limit * 2 - 1).join('') + '…'
        : chars.slice(limit).join('')].join('\n')
  return {
    id: entity.id,
    style: {
      x: position[0], y: position[1], size: center ? 146 : compact ? 62 : 110,
      fill: color.fill, stroke: center ? '#44a99c' : color.stroke, lineWidth: center ? 4 : 1.5,
      labelText: label, labelFill: color.text, labelFontWeight: 600,
      labelFontSize: center ? 15 : compact ? 11 : 13, labelPlacement: 'center', labelWordWrap: false,
      cursor: 'pointer',
    },
  }
}

export function toEdges(edges: Relation[], labels: boolean): EdgeData[] {
  const byPair = new Map<string, Relation[]>()
  for (const edge of edges) {
    const key = JSON.stringify([edge.source, edge.target].sort())
    const group = byPair.get(key) ?? []
    group.push(edge)
    byPair.set(key, group)
  }
  return [...byPair.values()].flatMap(group => group.map((edge, i) => {
    const offset = 28 * (i - (group.length - 1) / 2) * (edge.source <= edge.target ? 1 : -1)
    const stroke = edge.relationType === '导致' ? '#8a553c' : edge.directed ? '#587691' : '#8193a6'
    return {
      id: edge.id, source: edge.source, target: edge.target,
      type: edge.source === edge.target ? 'loop' : offset === 0 ? 'line' : 'quadratic',
      style: {
        curveOffset: offset, stroke, lineWidth: 1.5, increasedLineWidthForHitTesting: 10,
        endArrow: edge.directed, endArrowSize: 9, lineDash: edge.directed ? [] : [5, 4],
        labelText: edge.label, label: labels, labelFontSize: 12, labelFill: '#354e66',
        labelBackground: true, labelBackgroundFill: '#f7fafc', labelPadding: [2, 4],
        labelAutoRotate: false, cursor: 'pointer',
      },
    }
  }))
}
