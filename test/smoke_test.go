package test

import (
	"crypto/tls"
	"fmt"
	"os"
	"testing"
	"time"

	http_helper "github.com/gruntwork-io/terratest/modules/http-helper"
	"github.com/gruntwork-io/terratest/modules/k8s"
)

func TestSmoke(t *testing.T) {
	t.Parallel()

	var mainApps = []struct {
		name           string
		namespace      string
		expectedStatus int
	}{
		{"argocd-server", "argocd", 200},
		{"gitea", "gitea", 200},
		{"grafana", "grafana", 200},
		{"homepage", "homepage", 200},
		{"kanidm", "kanidm", 200},
		// DSH Web requires its startup token, so anonymous access is a 401.
		{"deepseek-harness", "deepseek-harness", 401},
		// noVNC is intentionally unauthenticated inside the tailnet.
		{"deepseek-harness-desktop", "deepseek-harness", 200},
	}

	for _, app := range mainApps {
		app := app // https://github.com/golang/go/wiki/CommonMistakes#using-goroutines-on-loop-iterator-variables
		t.Run(app.name, func(t *testing.T) {
			t.Parallel()

			options := k8s.NewKubectlOptions("", "", app.namespace)

			// Wait the service to become available to ensure that we can access it
			k8s.WaitUntilIngressAvailable(t, options, app.name, 30, 60*time.Second)

			// Now we verify that the service will successfully boot and start serving requests
			ingress := k8s.GetIngress(t, options, app.name)

			// Setup a TLS configuration, ignore the certificate because we may not use cert-manager (like the sandbox environment)
			tlsConfig := tls.Config{
				InsecureSkipVerify: os.Getenv("INSECURE_SKIP_VERIFY") != "",
			}

			// Test the endpoint with the status expected for this app (DSH returns 401 without a token).
			http_helper.HttpGetWithRetryWithCustomValidation(
				t,
				fmt.Sprintf("https://%s", ingress.Spec.Rules[0].Host),
				&tlsConfig,
				30,
				60*time.Second,
				func(statusCode int, body string) bool {
					return statusCode == app.expectedStatus
				},
			)
		})
	}
}
