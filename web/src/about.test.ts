/** What a part's page says about which way round it is. */
import { describe, expect, it } from 'vitest'

import { polarityOf } from './about'

describe('polarity', () => {
  it('is said once when every source agrees', () => {
    expect(polarityOf([['NPN', 'name', 'jis-c7012', ''], ['NPN', 'model', 'spice_definitions', 'https://x']]))
      .toEqual(['NPN'])
  })

  it('is not said when two sources answer the same question differently', () => {
    expect(polarityOf([['PNP', 'name', 'jis-c7012', ''], ['NPN', 'catalogue', 'sanken', 'https://x']])).toBeNull()
  })

  it('answers a bipolar and a channel apart', () => {
    expect(polarityOf([['NPN', 'model', 'a', ''], ['N-channel', 'model', 'a', '']])).toEqual(['NPN', 'N-channel'])
  })
})
