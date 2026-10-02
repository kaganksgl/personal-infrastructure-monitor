import { Box, SimpleGrid, Text, Tooltip } from "@mantine/core";

import type { SampleDetails } from "../../types/api";
import { formatNumber, formatPercent } from "../../utils/format";

/** Per-core utilisation as a compact grid of fill bars. */
export function CoreGrid({ cpu }: { cpu: SampleDetails["cpu"] }) {
  return (
    <>
      <SimpleGrid cols={{ base: 4, sm: 8, md: 12 }} spacing={6} verticalSpacing={6}>
        {cpu.per_core_percent.map((value, i) => (
          <Tooltip key={i} label={`Core ${i}: ${formatPercent(value)}`}>
            <Box
              role="meter"
              aria-label={`Core ${i}`}
              aria-valuenow={value}
              aria-valuemin={0}
              aria-valuemax={100}
              style={{
                height: 36,
                borderRadius: 4,
                border: "1px solid var(--mantine-color-default-border)",
                background: `linear-gradient(to top, var(--series-1) ${value}%, transparent ${value}%)`,
                position: "relative",
              }}
            >
              <Text size="10px" c="dimmed" style={{ position: "absolute", top: 1, left: 4 }}>
                {i}
              </Text>
            </Box>
          </Tooltip>
        ))}
      </SimpleGrid>
      <Text size="xs" c="dimmed" mt="xs">
        iowait {formatPercent(cpu.iowait_percent)} · steal {formatPercent(cpu.steal_percent)} · context switches{" "}
        {formatNumber(cpu.context_switches_per_sec, 0)}/s · interrupts {formatNumber(cpu.interrupts_per_sec, 0)}/s
      </Text>
    </>
  );
}
