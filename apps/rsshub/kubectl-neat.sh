#!/bin/bash

# 遍历 rsshub 下的所有子目录
for subdir in ./*/; do
    # 遍历子目录中的所有 .json 文件
    for json_file in "$subdir"*.json; do
        # 获取文件名（不带路径和扩展名）
        filename=$(basename "$json_file" .json)

        # 执行 kubectl neat 命令并将输出保存为 .yaml 文件
        kubectl neat -f "$json_file" --output yaml >"${subdir}${filename}.yaml"
    done
done
