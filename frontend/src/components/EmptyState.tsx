import { Center, Stack, Text, ThemeIcon } from "@mantine/core";
import type { ReactNode } from "react";

export function EmptyState({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children?: ReactNode;
}) {
  return (
    <Center py="xl">
      <Stack align="center" gap="xs" maw={460}>
        <ThemeIcon size={44} radius="xl" variant="light">
          {icon}
        </ThemeIcon>
        <Text fw={600}>{title}</Text>
        {children && (
          <Text size="sm" c="dimmed" ta="center">
            {children}
          </Text>
        )}
      </Stack>
    </Center>
  );
}
