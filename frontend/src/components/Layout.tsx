import {
  ActionIcon,
  AppShell,
  Burger,
  Group,
  Menu,
  NavLink,
  Text,
  Tooltip,
  useComputedColorScheme,
  useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconActivityHeartbeat,
  IconBell,
  IconLayoutDashboard,
  IconLogout,
  IconMoon,
  IconServer,
  IconSun,
  IconUser,
  IconAdjustmentsAlt,
} from "@tabler/icons-react";
import { NavLink as RouterLink, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { ConnectionIndicator } from "./ConnectionIndicator";

const NAV = [
  { to: "/", label: "Overview", icon: IconLayoutDashboard },
  { to: "/machines", label: "Machines", icon: IconServer },
  { to: "/alerts", label: "Alerts", icon: IconBell },
  { to: "/rules", label: "Alert rules", icon: IconAdjustmentsAlt },
];

function ThemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  const computed = useComputedColorScheme("light");
  const next = computed === "dark" ? "light" : "dark";
  return (
    <Tooltip label={`Switch to ${next} mode`}>
      <ActionIcon variant="default" size="lg" onClick={() => setColorScheme(next)} aria-label={`Switch to ${next} mode`}>
        {computed === "dark" ? <IconSun size={18} /> : <IconMoon size={18} />}
      </ActionIcon>
    </Tooltip>
  );
}

export function Layout() {
  const [opened, { toggle, close }] = useDisclosure();
  const { user, logout } = useAuth();
  const location = useLocation();

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 220, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="xs">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Toggle navigation" />
            <IconActivityHeartbeat size={24} color="var(--series-1)" aria-hidden />
            <Text fw={700} size="lg">
              InfraWatch
            </Text>
          </Group>
          <Group gap="sm">
            <ConnectionIndicator />
            <ThemeToggle />
            <Menu position="bottom-end" withArrow>
              <Menu.Target>
                <ActionIcon variant="default" size="lg" aria-label="Account menu">
                  <IconUser size={18} />
                </ActionIcon>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Label>
                  {user?.username} · {user?.role}
                </Menu.Label>
                <Menu.Item leftSection={<IconLogout size={16} />} onClick={() => void logout()}>
                  Sign out
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            component={RouterLink}
            to={item.to}
            label={item.label}
            leftSection={<item.icon size={18} />}
            active={item.to === "/" ? location.pathname === "/" : location.pathname.startsWith(item.to)}
            onClick={close}
          />
        ))}
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
