import type { Plugin } from 'vue'

/**
 * 全局插件：输入框按回车时自动失焦
 */
export const inputBlurOnEnterPlugin: Plugin = {
  install() {
    document.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key !== 'Enter') return
      
      const target = e.target as HTMLElement
      if (!target) return
      
      const tagName = target.tagName.toLowerCase()
      const isInput = tagName === 'input' || tagName === 'textarea'
      const isElInput = target.classList.contains('el-input__inner') || 
                        target.classList.contains('el-textarea__inner')
      
      if (isInput || isElInput) {
        target.blur()
      }
    })
  }
}
