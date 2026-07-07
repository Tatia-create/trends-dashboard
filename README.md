# 全球趋势仪表盘 · Global Trends Dashboard

> 每天 10:30 北京时间自动抓取全球 30+ 公开 RSS 源,自动部署到 GitHub Pages。
> 打开一个 URL,看当天热点。**0 手动。**

🌐 **在线访问:** https://tatia-create.github.io/trends-dashboard/

## 入口

- **📊 仪表盘(蓝绿色,信息密集型):** [/version-b-information-density.html](https://tatia-create.github.io/trends-dashboard/version-b-information-density.html)
- **📖 杂志版(思源宋体,大图,留白):** [/version-a-magazine.html](https://tatia-create.github.io/trends-dashboard/version-a-magazine.html)

## 自动化流程

```
沙箱 10:30 ──→ 推 GitHub
                  ↓
       GitHub Actions 兜底
       (每天 02:30 UTC = 北京 10:30)
                  ↓
       自动 commit + 自动 Pages 部署
                  ↓
       你打开 URL → 看到当天数据
```

**双重保险:**
- 沙箱里的 aily-schedule 任务(10:30 北京时间)每天推一次
- GitHub Actions cron 每天 02:30 UTC 也会跑一次

两层都跑 → 即便沙箱失败,GitHub Actions 也会接住。

## 信息源 (30+)

| 分类 | 源 |
|------|------|
| 美妆 | Glossy, Allure, WWD, Byrdie, Cosmetics Business, Beauty Independent |
| AI | TechCrunch, The Verge, VentureBeat, CB Insights, MIT Tech Review, 36Kr |
| 投融资 | Crunchbase, PitchBook, 36Kr, Bloomberg, Hacker News, IT 桔子 |
| 电商 | Modern Retail, Retail Brew, Practical Ecommerce, Digital Commerce 360, eMarketer |
| 研报 | 艾瑞咨询, 阿里研究院, QuestMobile, CBN Data, TalkingData, 艺恩 |
| 移动 | 36氪研究院, 智研咨询 |

## 文件结构

```
trends-dashboard/
├── version-a-magazine.html        杂志版
├── version-b-information-density.html  仪表盘
├── trends-data.json               数据(自动生成)
├── scripts/fetch_trends.py        抓取脚本
├── update.sh                      抓取+提交+推送
├── .github/workflows/daily-fetch.yml  GitHub Actions
└── README.md
```

## 数据格式

`trends-data.json` 包含:
- `stats`: 总数 / HOT / TRENDING / NEW / ARCHIVED
- `stories`: 最多 300 条故事(180 天窗口)
- 每条故事:`cat`(分类) / `heat`(热度) / `market`(市场) / `date` / `title` / `desc` / `source` / `sourceLabel`

## 维护

- 抓取脚本:`scripts/fetch_trends.py` (Python 3 stdlib only,无依赖)
- 添加新源:编辑 `SOURCES` 字典,提交后下次自动跑
- 修改数据窗口:`WINDOW_START` (默认 180 天)
- 每天 02:30 UTC / 10:30 北京时间自动跑

## License

数据均来自公开 RSS 源,所有内容归原作者。仅供个人/内部研究使用。
