# 使用 React、Vite、Ant Design 和集中主题

三个产品页面需要成熟的表格、表单、上传和可访问交互，同时必须符合已经冻结的 Apple 风格业务工作台视觉合同。团队并行开发还需要一套明确、有限的前端依赖，避免每个任务自行选择组件和样式方案。

前端使用 React、TypeScript 和 Vite。Ant Design 是唯一功能组件库，React Router 管路由，TanStack Query 管服务端状态，Ant Design Form 管表单，图标只使用 `@ant-design/icons`。Ant Design 通过 `ConfigProvider`、集中 CSS 变量和 CSS Modules 映射项目视觉令牌，不直接交付默认皮肤。

本期不引入 Tailwind CSS、Redux、Zustand、GSAP、Motion、第二套组件库或第二套图标族。增加新依赖前必须由当前需求证明必要，并检查其是否破坏视觉合同、包体和团队边界。
