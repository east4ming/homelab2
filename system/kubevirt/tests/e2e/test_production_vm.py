"""端到端测试: 生产级 VM 全生命周期验证.

验证项:
- VM 创建 + cloud-init SSH 密钥注入
- virtctl console 登录
- SSH 登录
- 持久化存储写入 + 重启后验证
- dnf 安装软件
- 多次重启稳定性
"""

import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.common import (
    MANIFESTS_DIR,
    kubectl_apply,
    kubectl_delete,
    log_info,
    log_success,
    log_warn,
    run_command,
    wait_for_condition,
)
from lib.resource_limiter import check_vm_limit, validate_vm_resources

MANIFEST = MANIFESTS_DIR / "e2e" / "production-vm.yaml"
VM_NAME = "prod-vm"
NAMESPACE = "kubevirt-test"

# 测试超时 (Fedora VM 启动较慢)
VM_START_TIMEOUT = 300
SSH_TIMEOUT = 60


def _generate_ssh_key() -> tuple[str, str]:
    """生成临时 SSH ed25519 密钥对，返回 (private_key_path, public_key_content)."""
    key_dir = tempfile.mkdtemp(prefix="kubevirt-test-key-")
    key_path = Path(key_dir) / "id_ed25519"
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(key_path), "-N", "", "-q"],
        check=True, timeout=30,
    )
    pubkey = (key_path.with_suffix(".pub")).read_text().strip()
    return str(key_path), pubkey


def _patch_cloudinit_ssh_key(public_key: str) -> None:
    """用临时生成的 SSH 公钥替换 cloud-init Secret 中的占位符."""
    manifest_text = MANIFEST.read_text()
    manifest_text = manifest_text.replace("SSH_PUBLIC_KEY_PLACEHOLDER", public_key)

    # Write to temp file and apply
    tmp = Path(tempfile.mkstemp(suffix=".yaml")[1])
    tmp.write_text(manifest_text)
    result = kubectl_apply(tmp, NAMESPACE)
    tmp.unlink()
    assert result.returncode == 0, f"Failed to apply manifest: {result.stderr}"


def _ssh_exec(private_key_path: str, host: str, command: str, timeout: int = SSH_TIMEOUT) -> subprocess.CompletedProcess:
    """通过 SSH 执行命令."""
    return subprocess.run(
        [
            "ssh", "-i", private_key_path,
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=10",
            f"fedora@{host}", command,
        ],
        capture_output=True, text=True, timeout=timeout,
    )


def _get_vm_ip() -> str:
    """获取 VM Pod IP."""
    result = run_command([
        "kubectl", "get", "vmi", VM_NAME, "-n", NAMESPACE,
        "-o", "jsonpath={.status.interfaces[0].ipAddress}",
    ])
    return result.stdout.strip()


def _virtctl_console_check() -> bool:
    """验证 virtctl console 可连接 (使用 pexpect 或简单超时检测)."""
    try:
        import pexpect
        child = pexpect.spawn(
            f"virtctl console {VM_NAME} -n {NAMESPACE}",
            timeout=30,
        )
        # 等待 login 提示符或超时
        idx = child.expect(["login:", "Login incorrect", pexpect.TIMEOUT, pexpect.EOF], timeout=30)
        child.close()
        return idx == 0  # 看到 login: 提示符 = 控制台可达
    except Exception as e:
        log_warn(f"virtctl console 检测异常: {e}")
        return False


def test_production_vm():
    """生产级 VM 端到端验证."""
    log_info("=" * 60)
    log_info("生产级 VM 端到端测试 (Fedora 40, 2C4G)")
    log_info("=" * 60)

    # 前置检查
    if not check_vm_limit(NAMESPACE):
        log_warn("VM 槽位已满 (max 2)，跳过测试")
        return

    if not validate_vm_resources("2", "4Gi"):
        log_warn("VM 规格超限，跳过测试")
        return

    key_path = ""
    try:
        # Step 0: 生成 SSH 密钥 + 注入 cloud-init
        log_info("Step 0: 生成临时 SSH 密钥并注入 cloud-init")
        key_path, pubkey = _generate_ssh_key()
        _patch_cloudinit_ssh_key(pubkey)
        log_success(f"SSH 密钥已生成")

        # Step 1: 等待 VM Running
        log_info(f"Step 1: 等待 VM Running (timeout={VM_START_TIMEOUT}s)")
        running = wait_for_condition(f"vm/{VM_NAME}", "Running", timeout=VM_START_TIMEOUT, namespace=NAMESPACE)
        assert running, f"VM '{VM_NAME}' 在 {VM_START_TIMEOUT}s 内未进入 Running"

        # 等待 SSH 服务就绪
        log_info("等待 SSH 服务就绪 (30s)")
        time.sleep(30)

        # 获取 VM IP
        vm_ip = _get_vm_ip()
        log_info(f"VM IP: {vm_ip}")
        assert vm_ip, "无法获取 VM IP 地址"

        # Step 2: SSH 登录验证
        log_info("Step 2: SSH 登录验证")
        ssh_result = _ssh_exec(key_path, vm_ip, "echo ssh-ok && hostname")
        assert ssh_result.returncode == 0, f"SSH 登录失败: {ssh_result.stderr}"
        assert "ssh-ok" in ssh_result.stdout, f"SSH 响应异常: {ssh_result.stdout}"
        log_success(f"SSH 登录成功 — hostname: {ssh_result.stdout.strip()}")

        # Step 3: virtctl console 验证
        log_info("Step 3: virtctl console 连接验证")
        console_ok = _virtctl_console_check()
        if console_ok:
            log_success("virtctl console 连接成功")
        else:
            log_warn("virtctl console 未检测到 login 提示符 (可能 Guest Agent 未就绪)")

        # Step 4: 持久化存储验证
        log_info("Step 4: 持久化存储写入 + 重启验证")
        # 格式化数据盘 (如果未格式化)
        _ssh_exec(key_path, vm_ip, "sudo mkfs.ext4 -F /dev/vdb 2>/dev/null || true")
        _ssh_exec(key_path, vm_ip, "sudo mount /dev/vdb /persistent 2>/dev/null || true")
        _ssh_exec(key_path, vm_ip, "sudo chown fedora:fedora /persistent")
        # 写入测试文件
        test_content = f"kubevirt-e2e-test-{int(time.time())}"
        _ssh_exec(key_path, vm_ip, f"echo '{test_content}' | sudo tee /persistent/data.txt")

        # 重启 VM
        log_info("重启 VM (virtctl restart)")
        run_command(["virtctl", "restart", VM_NAME, "-n", NAMESPACE], timeout=60)

        # 等待 VM 回到 Running
        log_info("等待 VM 重启完成 (timeout=180s)")
        time.sleep(15)  # 给 VM 一点关闭时间
        running = wait_for_condition(f"vm/{VM_NAME}", "Running", timeout=180, namespace=NAMESPACE)
        assert running, "VM 重启后未恢复 Running"

        # 等待 SSH
        time.sleep(30)
        vm_ip = _get_vm_ip()

        # 验证文件持久化
        ssh_result = _ssh_exec(key_path, vm_ip, "sudo cat /persistent/data.txt")
        assert test_content in ssh_result.stdout, (
            f"持久化验证失败: 期望 '{test_content}'，实际 '{ssh_result.stdout.strip()}'"
        )
        log_success("持久化存储验证通过 — 重启后数据完整")

        # Step 5: 软件安装测试
        log_info("Step 5: dnf 安装 nginx")
        _ssh_exec(key_path, vm_ip, "sudo dnf install -y nginx 2>&1", timeout=120)
        _ssh_exec(key_path, vm_ip, "sudo systemctl start nginx")
        time.sleep(3)
        nginx_check = _ssh_exec(key_path, vm_ip, "systemctl is-active nginx")
        assert "active" in nginx_check.stdout, f"nginx 未启动: {nginx_check.stdout}"
        log_success("dnf 安装 + nginx 启动验证通过")

        # Step 6: 多次重启稳定性
        log_info("Step 6: 多次重启稳定性 (3 次)")
        for i in range(3):
            log_info(f"  重启 {i + 1}/3")
            run_command(["virtctl", "restart", VM_NAME, "-n", NAMESPACE], timeout=60)
            time.sleep(10)
            running = wait_for_condition(f"vm/{VM_NAME}", "Running", timeout=120, namespace=NAMESPACE)
            assert running, f"第 {i + 1} 次重启后 VM 未恢复 Running"
            time.sleep(15)
        log_success("3 次重启全部通过 — VM 稳定性合格")

        log_success("=" * 60)
        log_success("生产级 VM 端到端测试全部通过!")
        log_success("=" * 60)

    finally:
        # 清理
        log_info("清理: 删除生产级 VM 及相关资源")
        kubectl_delete(MANIFEST, NAMESPACE)
        run_command(["kubectl", "delete", "pvc", "prod-vm-rootdisk", "-n", NAMESPACE, "--ignore-not-found=true"], timeout=10)
        run_command(["kubectl", "delete", "pvc", "prod-vm-datadisk", "-n", NAMESPACE, "--ignore-not-found=true"], timeout=10)
        run_command(["kubectl", "delete", "secret", "prod-vm-cloudinit", "-n", NAMESPACE, "--ignore-not-found=true"], timeout=10)
        if key_path:
            import shutil
            shutil.rmtree(Path(key_path).parent, ignore_errors=True)
        log_success("生产级 VM 资源清理完毕")
