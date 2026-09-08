import '@testing-library/jest-dom/vitest'

// 部分 jsdom 环境不提供 crypto.randomUUID（ReviewPanel 用它生成 submission_id）。
if (typeof globalThis.crypto === 'undefined' || typeof globalThis.crypto.randomUUID !== 'function') {
  Object.defineProperty(globalThis, 'crypto', {
    configurable: true,
    value: {
      ...(globalThis.crypto ?? {}),
      randomUUID: () => 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (character) => {
        const random = Math.floor(Math.random() * 16)
        const value = character === 'x' ? random : (random & 0x3) | 0x8
        return value.toString(16)
      }),
    },
  })
}