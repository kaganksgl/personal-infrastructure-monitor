import { Alert, Anchor, Button, Center, Paper, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";
import { IconActivityHeartbeat, IconAlertCircle } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";
import type { AuthStatus } from "../types/api";

export function LoginPage() {
  const { login, register } = useAuth();
  const [status, setStatus] = useState<AuthStatus>();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .authStatus()
      .then((s) => {
        setStatus(s);
        if (!s.has_users) setMode("register");
      })
      .catch(() => setError("Cannot reach the InfraWatch API."));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await (mode === "login" ? login(username, password) : register(username, password));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const firstUser = status && !status.has_users;

  return (
    <Center mih="100vh" p="md">
      <Paper p="xl" w="100%" maw={400} shadow="sm">
        <form onSubmit={submit}>
          <Stack>
            <Stack gap={4} align="center">
              <IconActivityHeartbeat size={36} color="var(--series-1)" aria-hidden />
              <Title order={2}>InfraWatch</Title>
              <Text size="sm" c="dimmed" ta="center">
                {firstUser
                  ? "Create the first account. It will be the administrator."
                  : mode === "login"
                    ? "Sign in to your monitoring dashboard"
                    : "Create a viewer account"}
              </Text>
            </Stack>
            {error && (
              <Alert color="red" icon={<IconAlertCircle size={16} />} role="alert">
                {error}
              </Alert>
            )}
            <TextInput
              label="Username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.currentTarget.value)}
              required
              minLength={3}
            />
            <PasswordInput
              label="Password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              description={mode === "register" ? "At least 10 characters" : undefined}
              value={password}
              onChange={(e) => setPassword(e.currentTarget.value)}
              required
              minLength={mode === "register" ? 10 : undefined}
            />
            <Button type="submit" loading={busy} fullWidth>
              {mode === "login" ? "Sign in" : "Create account"}
            </Button>
            {status?.registration_open && status.has_users && (
              <Text size="sm" ta="center">
                <Anchor component="button" type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}>
                  {mode === "login" ? "Create an account" : "Back to sign in"}
                </Anchor>
              </Text>
            )}
          </Stack>
        </form>
      </Paper>
    </Center>
  );
}
