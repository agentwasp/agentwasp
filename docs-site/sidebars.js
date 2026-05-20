// @ts-check

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  docs: [
    {
      type: 'doc',
      id: 'index',
      label: 'Introduction',
    },
    {
      type: 'category',
      label: 'Getting Started',
      collapsed: false,
      items: [
        'getting-started/installation',
        'getting-started/docker-setup',
        'getting-started/environment-variables',
        'getting-started/first-launch',
        'getting-started/dashboard-access',
      ],
    },
    {
      type: 'category',
      label: 'Core Concepts',
      items: [
        'core-concepts/agent-architecture',
        'core-concepts/goal-engine',
        'core-concepts/skills',
        'core-concepts/memory',
        'core-concepts/knowledge-graph',
        'core-concepts/scheduler',
        'core-concepts/resource-governor',
      ],
    },
    {
      type: 'category',
      label: 'Cognitive Systems',
      items: [
        'cognitive-systems/world-model',
        'cognitive-systems/temporal-reasoning',
        'cognitive-systems/plan-critic',
        'cognitive-systems/skill-evolution',
        'cognitive-systems/behavioral-learning',
        'cognitive-systems/opportunity-engine',
        'cognitive-systems/reflection-engine',
      ],
    },
    {
      type: 'category',
      label: 'System Architecture',
      items: [
        'architecture/runtime',
        'architecture/context-builder',
        'architecture/orchestration',
        'architecture/execution-pipeline',
      ],
    },
    {
      type: 'category',
      label: 'Integrations',
      items: [
        'integrations/telegram',
        'integrations/dashboard',
        'integrations/api',
      ],
    },
    {
      type: 'category',
      label: 'Operations',
      items: [
        'operations/commands',
        'operations/configuration',
        'operations/logs',
        'operations/monitoring',
        'operations/scaling',
      ],
    },
    {
      type: 'category',
      label: 'Security',
      items: [
        'security/sandboxing',
        'security/skill-safety',
        'security/privilege-boundaries',
        'security/audit-logs',
        'security/testing-and-audit',
      ],
    },
    {
      type: 'category',
      label: 'Development',
      items: [
        'development/project-structure',
        'development/creating-skills',
        'development/extending',
      ],
    },
    {
      type: 'category',
      label: 'Advanced',
      items: [
        'advanced/autonomous-goals',
        'advanced/agent-orchestration',
        'advanced/reflection',
        'advanced/capability-evolution-engine',
      ],
    },
    {
      type: 'category',
      label: 'Troubleshooting',
      items: [
        'troubleshooting/common-errors',
        'troubleshooting/debugging',
      ],
    },
    {
      type: 'doc',
      id: 'known-limitations',
      label: 'Known Limitations',
    },
    {
      type: 'doc',
      id: 'roadmap',
      label: 'Roadmap',
    },
    {
      type: 'doc',
      id: 'changelog',
      label: 'Changelog',
    },
  ],
};

export default sidebars;
