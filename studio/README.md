# Flo AI Studio

A powerful visual designer for creating YAML-based AI agent workflows. Build complex multi-agent workflows with an intuitive drag-and-drop interface, configure agents with comprehensive forms, set up routing logic, and export everything as production-ready YAML.

## 🌟 Overview

Flo AI Studio is a React-based visual editor that makes it easy to design and configure AI workflows for the Flo AI framework. It provides a user-friendly interface for creating complex agent orchestrations without writing code.

## ✨ Features

- **🎨 Visual Workflow Design**: Drag-and-drop interface using React Flow
- **🤖 Agent Management**: Create and edit agents with comprehensive configuration forms
- **🔧 Tool Integration**: Add and configure tools for your agents
- **🔀 Router Configuration**: Define custom routing logic between workflow nodes
- **📄 YAML Export**: Generate production-ready YAML configurations
- **📋 Template System**: Quick agent templates for common use cases
- **⚙️ Configuration Management**: Manage available tools, LLMs, and routers
- **💾 State Management**: Robust state management with Zustand
- **🎯 TypeScript**: Fully typed for better development experience

## 🚀 Quick Start

### Installation

```bash
# Navigate to flo_studio directory
cd flo_studio

# Install dependencies
pnpm install

# Start development server
pnpm dev
```

### Building for Production

```bash
# Build the application
pnpm build

# Preview the build
pnpm preview
```

## 🏗️ Architecture

### Project Structure

```
flo_studio/
├── src/
│   ├── components/          # React components
│   │   ├── editors/         # Modal editors (Agent, Edge, Config)
│   │   ├── flow/           # React Flow components
│   │   ├── sidebar/        # Sidebar components
│   │   ├── toolbar/        # Toolbar components
│   │   └── ui/             # Reusable UI components
│   ├── store/              # Zustand store
│   ├── types/              # TypeScript definitions
│   ├── utils/              # Utility functions
│   └── lib/                # Shared utilities
├── public/                 # Static assets
└── dist/                   # Build output
```

### Key Technologies

- **React 18** - Modern React with hooks and concurrent features
- **TypeScript** - Type safety and better developer experience
- **React Flow** - Graph visualization and interaction
- **Zustand** - Lightweight state management
- **Tailwind CSS** - Utility-first CSS framework
- **Radix UI** - Accessible component primitives
- **React Hook Form** - Form handling with validation
- **js-yaml** - YAML parsing and generation
- **Vite** - Fast build tool and dev server

## 🎯 Usage Guide

### Creating Your First Workflow

1. **Start the Application**
   ```bash
   pnpm dev
   ```

2. **Create an Agent**
   - Click the "Agent" button in the toolbar
   - Fill in the agent configuration form:
     - Name and role
     - Job description
     - LLM model selection
     - Tools (optional)
     - Output parser (optional)

3. **Build the Workflow**
   - Drag nodes from the sidebar onto the canvas
   - Connect nodes by dragging from output handles to input handles
   - Configure edge routers by clicking on connections

4. **Export Configuration**
   - Click "Export" in the toolbar
   - Review the generated YAML
   - Download or copy the configuration

### Agent Configuration

Agents can be configured with:

- **Basic Information**: Name, role, job description
- **Model Settings**: Provider (OpenAI, Anthropic, etc.), model name, temperature
- **Tools**: Select from available tools or add custom ones
- **Output Parser**: Define structured output schemas
- **Reasoning Pattern**: DIRECT, COT (Chain of Thought), or REACT

### Workflow Features

- **Visual Connections**: Drag to connect agents and tools
- **Router Functions**: Configure conditional routing between nodes
- **Start/End Nodes**: Automatically detected based on connections
- **Validation**: Real-time validation of workflow structure

## 🔧 Configuration

### Available LLMs

The studio comes pre-configured with popular LLM providers:

- **OpenAI**: GPT-4o, GPT-4o-mini
- **Anthropic**: Claude-3.5-Sonnet, Claude-3.5-Haiku
- **Google**: Gemini-2.5-Flash, Gemini-2.5-Pro
- **Ollama**: Llama2, Llama3 (local models)

### Available Tools

Default tools include:

- **calculator** - Mathematical calculations
- **web_search** - Web search functionality
- **file_reader** - File reading and analysis
- **email_sender** - Email sending capabilities
- **text_processor** - Text processing and analysis
- **image_analyzer** - Image analysis and processing

### Router Functions

Pre-configured router functions:

- **default_router** - Simple pass-through routing
- **content_router** - Routes based on content analysis
- **classification_router** - Routes based on classification results
- **sentiment_router** - Routes based on sentiment analysis

## 📊 YAML Export Format

The studio generates YAML compatible with the Flo AI framework:

```yaml
metadata:
  name: "My Workflow"
  version: "1.0.0"
  description: "Generated with Flo AI Studio"
  tags: ["flo-ai", "studio-generated"]

arium:
  agents:
    - name: "content_analyzer"
      role: "Content Analyst"
      job: "Analyze content and extract insights"
      model:
        provider: "openai"
        name: "gpt-4o-mini"
      settings:
        temperature: 0.3
        reasoning_pattern: "COT"
      
  workflow:
    start: "content_analyzer"
    edges:
      - from: "content_analyzer"
        to: ["summarizer"]
    end: ["summarizer"]
```

## 🔌 Integration with Flo AI

Use the exported YAML with the Flo AI framework:

```python
from flo_ai.arium.builder import AriumBuilder

# Load your exported workflow
builder = AriumBuilder.from_yaml(yaml_file="my-workflow.yaml")

# Run the workflow
result = await builder.build_and_run(["Your input here"])
```

## 🛠️ Development

### Adding New Components

1. **Create Component**
   ```typescript
   // src/components/MyComponent.tsx
   import React from 'react';
   
   export const MyComponent: React.FC = () => {
     return <div>My Component</div>;
   };
   ```

2. **Add to Store** (if needed)
   ```typescript
   // src/store/designerStore.ts
   interface DesignerState {
     // Add new state properties
     myNewFeature: boolean;
     setMyNewFeature: (value: boolean) => void;
   }
   ```

### Adding New Tool Templates

Edit the store configuration:

```typescript
// src/store/designerStore.ts
const defaultConfig: DesignerConfig = {
  availableTools: [
    // Add new tools
    { name: 'my_tool', description: 'My custom tool' },
  ],
  // ...
};
```

### Customizing Themes

Update CSS variables in `src/index.css`:

```css
:root {
  --primary: 222.2 47.4% 11.2%;
  --primary-foreground: 210 40% 98%;
  /* Add custom colors */
}
```

## 🐛 Troubleshooting

### Common Issues

1. **Build Errors**
   - Ensure all dependencies are installed: `pnpm install`
   - Clear node_modules and reinstall if needed

2. **TypeScript Errors**
   - Check type definitions in `src/types/`
   - Ensure proper imports and exports

3. **React Flow Issues**
   - Verify React Flow version compatibility
   - Check node and edge data structures

### Performance Optimization

- Use React.memo for heavy components
- Implement virtual scrolling for large workflows
- Optimize store subscriptions with selectors

## 🚀 Deployment

### Building for Production

```bash
# Build the application
pnpm build

# The dist/ folder contains the built application
```

### Deployment Options

- **Static Hosting**: Deploy `dist/` to Netlify, Vercel, or GitHub Pages
- **Docker**: Create a Docker container with nginx
- **CDN**: Upload to S3 + CloudFront or similar

### Environment Variables

Create `.env` files for different environments:

```bash
# .env.development
VITE_API_URL=http://localhost:3000

# .env.production
VITE_API_URL=https://api.myapp.com
```

## 📈 Roadmap

### Phase 1 (Current)
- ✅ Basic visual editor
- ✅ Agent configuration
- ✅ YAML export
- ✅ TypeScript support

### Phase 2 (Planned)
- [ ] YAML import functionality
- [ ] Workflow validation
- [ ] Advanced routing configuration
- [ ] Template library

### Phase 3 (Future)
- [ ] Real-time collaboration
- [ ] Workflow simulation
- [ ] Plugin system
- [ ] Cloud deployment

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make changes and add tests
4. Commit: `git commit -am 'Add my feature'`
5. Push: `git push origin feature/my-feature`
6. Create a Pull Request

### Development Guidelines

- Use TypeScript for all new code
- Follow the existing component structure
- Add proper error handling
- Write meaningful commit messages
- Update documentation as needed

## 📄 License

This project is part of the Flo AI framework and follows the same licensing terms.

## 🙏 Acknowledgments

- Built for the [Flo AI framework](../flo_ai/)
- Powered by React Flow for graph visualization
- UI components from Radix UI
- Icons from Lucide React

---

**Happy Building! 🚀**

For more information about the Flo AI framework, check out the [main documentation](../flo_ai/README.md).
