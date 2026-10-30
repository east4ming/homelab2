package test

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/gruntwork-io/terratest/modules/k8s"
)

// TestNodeAddressing 验收节点 IPv6 身份使用固定站点 ULA，而不是 ISP 下发的 GUA。
//
// 背景：ISP 的 240e 前缀会随 PPPoE 重拨/重启漂移，2026-10-29 就漂移过一次，
// 导致 node-ip 指向不存在的地址、Cilium 装不出跨节点 IPv6 直连路由。
// 地址规划与取舍见 specs/012-stable-node-ula-ipv6/plan.md。
//
// 需要 kubeconfig（人工验收，不在 CI 中执行）：
//
//	make -C test filter=NodeAddressing
func TestNodeAddressing(t *testing.T) {
	t.Parallel()

	// hostname -> 期望的 IPv6，与 metal/inventories/prod.yml 的 node_ipv6 一致
	expectedIPv6 := map[string]string{
		"n100-jumper-0": "fdb5:92d0:b067:1::11",
		"n100-jumper-1": "fdb5:92d0:b067:1::12",
		"n100-jumper-2": "fdb5:92d0:b067:1::13",
		"n100-cheshi-0": "fdb5:92d0:b067:1::14",
	}

	options := k8s.NewKubectlOptions("", "", "")

	out, err := k8s.RunKubectlAndGetOutputE(t, options, "get", "nodes", "-o", "json")
	if err != nil {
		t.Fatalf("kubectl get nodes failed: %v", err)
	}

	var nodeList struct {
		Items []struct {
			Metadata struct {
				Name string `json:"name"`
			} `json:"metadata"`
			Status struct {
				Addresses []struct {
					Type    string `json:"type"`
					Address string `json:"address"`
				} `json:"addresses"`
			} `json:"status"`
		} `json:"items"`
	}
	if err := json.Unmarshal([]byte(out), &nodeList); err != nil {
		t.Fatalf("decode nodes: %v", err)
	}

	if len(nodeList.Items) != len(expectedIPv6) {
		t.Fatalf("集群节点数 %d 与地址规划的 %d 不一致：先更新 expectedIPv6 再跑", len(nodeList.Items), len(expectedIPv6))
	}

	for _, node := range nodeList.Items {
		node := node
		name := node.Metadata.Name

		t.Run(name, func(t *testing.T) {
			t.Parallel()

			want, ok := expectedIPv6[name]
			if !ok {
				t.Fatalf("节点 %s 不在地址规划里", name)
			}

			var v6 []string
			for _, addr := range node.Status.Addresses {
				if addr.Type == "InternalIP" && strings.Contains(addr.Address, ":") {
					v6 = append(v6, addr.Address)
				}
			}
			if len(v6) != 1 {
				t.Fatalf("节点 %s 应当只有一个 IPv6 InternalIP，实际 %v", name, v6)
			}

			if v6[0] != want {
				t.Errorf("节点 %s 的 IPv6 InternalIP = %s，期望 %s（GUA 不能再当节点身份）", name, v6[0], want)
			}
		})
	}
}
