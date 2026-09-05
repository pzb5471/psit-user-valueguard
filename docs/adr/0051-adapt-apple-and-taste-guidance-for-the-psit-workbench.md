# 将 Apple 视觉语言和 taste-skill 通用规则适配到 PSIT 工作台

用户指定 `DESIGN-apple.md` 作为前端视觉依据，并要求吸收 GitHub `Leonxlnx/taste-skill` 的审美规范。两份材料都不能原样套用：前者主要分析 Apple 营销与商店页面，后者的默认 Skill 明确说明不适用于 dashboard、数据表格和多步骤产品界面；其 `gpt-taste` 变体还强制 AIDA、随机布局、GSAP 动画和巨大留白，与 PSIT 的售后运营工作台冲突。

项目采用 Apple 视觉语言中的单一动作蓝、白色与浅灰表面、清楚字体层级、8px 间距节奏、胶囊主操作、统一圆角、弱边界和克制动效；采用 taste-skill 中的产品类型判断、避免 AI 默认审美、颜色与形状一致、完整交互状态、表单标签、对比度、44px 点击区域和发布前视觉检查。固定设计参数为 `DESIGN_VARIANCE=3`、`MOTION_INTENSITY=2`、`VISUAL_DENSITY=6`。

不采用 Apple 官网的产品摄影、全屏产品 Tile 和巨大 Hero，也不采用 AIDA、Bento 工作流、GSAP、视差、随机版式、假截图、装饰性渐变、卡片投影和运行时外部素材。最终产品是 Apple 风格的业务工作台，不是 Apple 官网仿站。完整适配规则以 `docs/PSIT前端视觉与交互规范.md` 为准。

GitHub 来源固定到提交 `ccbc15639c97057cbfcf32ecebc38ef716e4bb37`。外部 Skill 只作为只读设计参考，不安装、不执行其中命令，也不允许覆盖项目安全、业务和技术边界。
