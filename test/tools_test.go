package test

import (
	"path/filepath"
	"testing"

	"github.com/gruntwork-io/terratest/modules/shell"
	"github.com/gruntwork-io/terratest/modules/version-checker"
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
		{"git", "--version", ">= 2.54.0, < 3.0.0"},
		{"go", "version", ">= 1.26.0, < 1.27.0"},
		{"helm", "version", ">= 3.20.0, < 4.0.0"},
		// Cluster runs v1.36.5+k3s1; keep kubectl inside the +/-1 minor skew window
		// https://kubernetes.io/releases/version-skew-policy/#kubectl
		{"kubectl", "version", ">= 1.36.0, < 1.37.0"},
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
}

func TestToolsNixShell(t *testing.T) {
	t.Parallel()

	projectRoot, err := filepath.Abs("../")
	if err != nil {
		t.FailNow()
	}

	command := shell.Command{
		Command: "nix",
		Args: []string{
			"develop",
			"--experimental-features", "nix-command flakes",
			"--command", "true",
		},
		WorkingDir: projectRoot,
	}

	shell.RunCommand(t, command)
}
