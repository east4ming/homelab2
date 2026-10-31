package test

import (
	"path/filepath"
	"regexp"
	"testing"

	"github.com/gruntwork-io/terratest/modules/shell"
	"github.com/gruntwork-io/terratest/modules/version-checker"
	"github.com/hashicorp/go-version"
)

func TestToolsVersions(t *testing.T) {
	t.Parallel()

	var tools = []struct {
		binaryPath        string
		versionArg        string
		versionConstraint string
	}{
		{"ansible", "--version", ">= 2.21.0, < 2.22.0"},
		{"docker", "--version", ">= 29.0.0, < 30.0.0"},
		{"git", "--version", ">= 2.47.0, < 3.0.0"},
		{"go", "version", ">= 1.26.0, < 1.27.0"},
		{"helm", "version", ">= 3.20.0, < 4.0.0"},
		{"kustomize", "version", ">= 5.8.0, < 6.0.0"},
		{"pre-commit", "--version", ">= 4.5.0, < 5.0.0"},
		{"tofu", "--version", ">= 1.11.0, < 2.0.0"},
	}

	for _, tool := range tools {
		tool := tool // https://github.com/golang/go/wiki/CommonMistakes#using-goroutines-on-loop-iterator-variables
		t.Run(tool.binaryPath, func(t *testing.T) {
			t.Parallel()
			params := version_checker.CheckVersionParams{
				BinaryPath:        tool.binaryPath,
				VersionConstraint: tool.versionConstraint,
				VersionArg:        tool.versionArg,
				WorkingDir:        ".",
			}

			version_checker.CheckVersion(t, params)
		})
	}

	// `kubectl version` also queries the API server and exits non-zero when no
	// cluster is reachable (CI has no kubeconfig), so only the client version is
	// checked here.
	t.Run("kubectl", func(t *testing.T) {
		t.Parallel()

		output := shell.RunCommandAndGetOutput(t, shell.Command{
			Command:    "kubectl",
			Args:       []string{"version", "--client"},
			WorkingDir: ".",
		})

		match := regexp.MustCompile(`Client Version:\s*v(\d+(\.\d+)+)`).FindStringSubmatch(output)
		if match == nil {
			t.Fatalf("cannot parse kubectl client version from output: %q", output)
		}

		clientVersion, err := version.NewVersion(match[1])
		if err != nil {
			t.Fatalf("invalid kubectl client version %q: %v", match[1], err)
		}

		// Cluster runs v1.36.5+k3s1; keep kubectl inside the +/-1 minor skew window
		// https://kubernetes.io/releases/version-skew-policy/#kubectl
		constraint, err := version.NewConstraint(">= 1.36.0, < 1.37.0")
		if err != nil {
			t.Fatalf("invalid kubectl version constraint: %v", err)
		}

		if !constraint.Check(clientVersion) {
			t.Fatalf("kubectl client version %s does not satisfy %s", clientVersion, constraint)
		}
	})
}

func TestToolsDevEnv(t *testing.T) {
	t.Parallel()

	projectRoot, err := filepath.Abs("../")
	if err != nil {
		t.FailNow()
	}

	// mise 能解析并加载项目工具环境。
	shell.RunCommand(t, shell.Command{
		Command:    "mise",
		Args:       []string{"exec", "--", "true"},
		WorkingDir: projectRoot,
	})

	// uv 环境已包含脚本运行所需的 Python 依赖。
	shell.RunCommand(t, shell.Command{
		Command:    "uv",
		Args:       []string{"run", "--frozen", "python", "-c", "import rich, kubernetes, pexpect, jinja2, netaddr"},
		WorkingDir: projectRoot,
	})
}
