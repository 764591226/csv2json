# csv2json

一个零依赖的 Python 命令行工具，把 CSV 转换成 JSON。只使用标准库，流式读写，大文件也不会一次性载入内存。

## 安装

```bash
pip install .
```

或者用 [pipx](https://pipx.pypa.io/) 装成全局命令：

```bash
pipx install .
```

不安装也可以直接运行：

```bash
python -m csv2json data.csv
```

## 用法

```bash
csv2json data.csv                    # JSON 数组输出到 stdout
csv2json data.csv -o data.json       # 写入文件
cat data.csv | csv2json              # 从 stdin 读
cat data.csv | csv2json --ndjson     # JSON Lines：每行一个对象
csv2json data.csv --types --indent 2 # 推断类型并格式化
```

示例：

```bash
$ printf 'name,age\nalice,30\nbob,41\n' | csv2json --types --indent 2
[
  {
    "name": "alice",
    "age": 30
  },
  {
    "name": "bob",
    "age": 41
  }
]
```

## 选项

| 选项 | 说明 |
| --- | --- |
| `INPUT` | CSV 文件路径；省略或写 `-` 表示从 stdin 读取 |
| `-o, --output FILE` | 输出到文件；省略则写 stdout（始终 UTF-8 编码） |
| `-d, --delimiter CHAR` | 分隔符，默认 `,`；用 `'\t'` 表示制表符 |
| `--encoding ENC` | 输入编码，默认 `utf-8-sig`（会顺带去掉 BOM） |
| `--no-header` | 输入没有表头，键名为 `column_1`、`column_2`…… |
| `--types` | 推断整数、浮点、布尔和空值，否则所有值都是字符串 |
| `--ndjson` | 输出 JSON Lines，而不是数组 |
| `--indent N` | 数组按 N 个空格缩进格式化 |
| `--version` | 显示版本号 |

## 行为说明

- **默认不推断类型。** 所有字段都输出为字符串，结果可预测，`00123` 之类不会变形。
- **`--types` 的规则：**
  - 整数、带小数或指数的数字 → JSON 数字；
  - `true` / `false`（不区分大小写）→ JSON 布尔；
  - 空字段 → `null`；
  - 前导零数字（如 `007`）、`nan`、`inf` → 保持字符串，避免丢信息或产生非法 JSON。
- **表头：** 表头会去掉首尾空白；出现重复列名时直接报错，避免静默丢列。
- **行列不齐：** 短行用空字符串补齐；长行报错并给出数据行号（表头算第 1 行）。
- **空文件：** 输出 `[]`；`--ndjson` 则输出空。
- **换行：** 输出文件统一使用 `\n`。

## 退出码

| 码 | 含义 |
| --- | --- |
| `0` | 成功 |
| `1` | 转换失败（文件无法打开、CSV 格式错误等） |
| `2` | 命令行参数错误 |

## 开发

```bash
python -m unittest discover -s tests -v
```

## 许可

MIT，见 [LICENSE](LICENSE)。
