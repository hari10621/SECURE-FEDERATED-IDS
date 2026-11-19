import {
  BarChart3,
  Cpu,
  Database,
  History,
  LayoutDashboard,
  Lock,
  Network,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Users,
  Activity,
  type LucideIcon,
} from 'lucide-react'

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
  description: string
}

export interface NavSection {
  title: string
  items: NavItem[]
}

export const NAV_SECTIONS: NavSection[] = [
  {
    title: 'Operations',
    items: [
      {
        to: '/',
        label: 'Overview',
        icon: LayoutDashboard,
        end: true,
        description: 'System health and recent activity',
      },
      {
        to: '/training',
        label: 'Federated Training',
        icon: Cpu,
        description: 'Experiments, jobs, and round metrics',
      },
      {
        to: '/clients',
        label: 'Federated Clients',
        icon: Users,
        description: 'Client configuration records',
      },
      {
        to: '/history',
        label: 'Experiment History',
        icon: History,
        description: 'Completed and failed experiment records',
      },
    ],
  },
  {
    title: 'Data',
    items: [
      {
        to: '/datasets',
        label: 'Datasets',
        icon: Database,
        description: 'Upload and validate local CSV datasets',
      },
      {
        to: '/performance',
        label: 'Performance Evaluation',
        icon: BarChart3,
        description: 'Metrics from completed local runs',
      },
    ],
  },
  {
    title: 'Security',
    items: [
      {
        to: '/encryption',
        label: 'Homomorphic Encryption',
        icon: Lock,
        description: 'CKKS availability and constraints',
      },
      {
        to: '/security',
        label: 'Security Monitoring',
        icon: ShieldCheck,
        description: 'Authentication and audit status',
      },
      {
        to: '/intrusion',
        label: 'Intrusion Detection',
        icon: Activity,
        description: 'Verified model inference status',
      },
      {
        to: '/sdn',
        label: 'SDN Network',
        icon: Network,
        description: 'Controller integration status',
      },
      {
        to: '/ips',
        label: 'IPS & Prevention',
        icon: ShieldAlert,
        description: 'Prevention actions and lab requirements',
      },
    ],
  },
  {
    title: 'System',
    items: [
      {
        to: '/settings',
        label: 'Settings',
        icon: Settings,
        description: 'API connection and local console options',
      },
    ],
  },
]

export const NAV_ITEMS: NavItem[] = NAV_SECTIONS.flatMap((section) => section.items)
