# 大模型与智能体如何检测内部威胁

近一年顶级会议的论文与数据集调研

检索窗口　2025 年 11 月 18 日至 2026 年 11 月 18 日

## 1 研究结论

从文献角度，WWW 2026 的 Insight-LLM 和 ICASSP 2026 的 LLMBA 仍是理解员工日志大模型检测的重要工作。两篇都用 CERT 评估检测器。如果目标是构建训练或评测数据，NDSS 2026 的 Chimera 提供组织级模拟和跨数据集实验。由于前两篇没有可核验的官方检测代码，Morpheus 的可复现实验改用 MOLE 的开源监测器。 [Insight-LLM 论文](https://doi.org/10.1145/3774904.3792398) · [ICASSP 论文](https://doi.org/10.1109/ICASSP55912.2026.11463924) · [NDSS 正式论文](https://www.ndss-symposium.org/ndss-paper/chimera-harnessing-multi-agent-llms-for-automatic-insider-threat-simulation/)

### 主实验的开源性更新

Insight-LLM 和 MARS-ITD 的论文入口可以核验，但截至 2026-11-23 没有找到可核验的官方检测代码。Morpheus 主实验因此改用开源的 MOLE 仓库。MOLE 提供 Apache-2.0 代码、账号日审计事件、标签、LLM 语义监测器、递归式 Agent 监测器和预算式级联监测器。实验固定使用 MOLE-Cascade 与 MOLE-RLM，并将 CERT user-day 和 Morpheus employee-day 转换为统一的账号日事件接口。 [MOLE 代码](https://github.com/aashiqmuhamed/mole) · [MOLE 论文](https://arxiv.org/abs/2609.06966) · [MOLE 数据](https://huggingface.co/datasets/forgelab/mole)

| 研究问题 | 优先阅读 | 论文实际测量的对象 |
| --- | --- | --- |
| 哪些员工行为值得调查？ | Insight-LLM、LLMBA | 在 CERT 合成员工活动上识别威胁。前者比较多视图融合，后者学习上下文和时间规律。 |
| 如何取得带标签的组织日志？ | Morpheus、OrgForge-IT | 前者产生跨组织的多模态遥测。后者用确定性引擎生成真值，可追查误报和责任归属。 |
| 组织内的 AI 账号造成损害时，审计员能否发现？ | MOLE、ICLR 的轨迹监测论文 | MOLE 按账号日排序，核验服务状态。ICLR 工作按任务轨迹筛查，评估人工复核后的召回。 |

### 同一检测器换到新组织会怎样

Morpheus 的 DS-IID 检测器在 CERT r6.2 同域实验中 F1 为 0.955。用 CERT 训练、测试于模拟金融组织时降至 0.464，调换训练与测试方向后为 0.739。CERT 同域成绩对新组织的预测能力有限。若只能先做一组复现实验，这三个值对应的协议比单个最高 F1 更值得复核。 [NDSS 全文](https://www.ndss-symposium.org/wp-content/uploads/2026-f375-paper.pdf)

### 主会目录中的直接命中

以已举办会议为口径，NeurIPS 2025、ICLR 2026、ICML 2026 主会目录中，未检出同时使用大模型或 Agent、以员工为被检测主体、并在内部威胁行为数据上评测的论文。三会有直接评估 AI Agent 轨迹的工作。OrgForge-IT、两阶段风险指标方法和 MOLE 以窗口内预印本收录。覆盖范围和可复查的目录见末页。

## 2 员工日志上的大模型检测

### Insight-LLM 把新增行为视图接入同一个检测器

Chengyu Song 等 · WWW 2026 研究论文。Fusion Is Not A Simple Ensemble! Towards The Evolving Views in Insider Threat Detection。四类视图分别采用 RoBERTa（文本）、TweetEval（情感）、TS2Vec（时间序列）和 Node2Vec（拓扑）提取表示。冻结的预训练编码器输出经 ViewAdapter 对齐到 LLM 的共同语义空间，再由上下文自适应模块加权，并与任务提示一同用于轻量微调。图 8 还比较了 BERT Large、RoBERTa Large、Llama 3.2 1B 和 Llama 3 8B，图中没有把某个基座标为默认配置。

正式论文图表给出了两个 CERT 版本的绝对结果。CERT r4.2 含 930 名正常员工、70 名恶意员工，32,762,906 条正常活动和 7,316 条异常活动。CERT r5.2 含 1,901 名正常员工、99 名恶意员工，79,846,358 条正常活动和 10,306 条异常活动，两个版本均覆盖 18 个月及 logon、email、device、http、file、psychometric 日志。Insight-LLM 的 F1/FPR 分别为 r4.2 的 0.9712/0.0476 和 r5.2 的 0.9594/0.0496。相对表中 LAN 基线，F1 提升 2.3% 和 4.8%，FPR 下降 61.0% 和 42.7%。摘要所说的“F1 最多提升 4.8%、误报减少 61%”对应这两组不同版本。相对简单集成法，新增视图的训练时间最多减少 83.2%。 [Insight-LLM 论文](https://doi.org/10.1145/3774904.3792398) · [表 1 图像](https://figures.semanticscholar.org/3016b10386488e4e9fb7f2c7f123093c8c1ee373/7-Table1-1.png) · [表 4 图像](https://figures.semanticscholar.org/3016b10386488e4e9fb7f2c7f123093c8c1ee373/11-Table4-1.png) · [可读摘要](https://api.openalex.org/works/https://doi.org/10.1145/3774904.3792398)

### LLMBA 把时间和行为上下文纳入预训练

Yan 等 · ICASSP 2026。LLMBA: Adapting Large Language Models for Behavior Analytics in Zero Trust Networks。作者用时间与上下文编码表达用户行为，通过自监督微调学习正常行为规律，再在 CERT 上识别异常。零信任场景关心的是账号获准进入网络后，持续发生的行为是否偏离历史。

同一研究组在 IEEE TIFS 2026 的 LLMBA: Efficient Behavior Analytics via Large Pretrained Models in Zero Trust Networks 中还讨论了知识蒸馏与部署成本。两文采用同一方法名，按一条研究路线阅读。已核的公开摘要没有给出可对齐的版本、样本单位或绝对分数。 [ICASSP 论文](https://doi.org/10.1109/ICASSP55912.2026.11463924) · [TIFS 期刊论文](https://doi.org/10.1109/TIFS.2026.3666459)

### 两阶段零样本检测暴露了采样带来的差异

Abdullah Alghamdi、Siamak Layeghy、Marius Portmann · arXiv，2026 年 8 月。LLMs for Zero-Shot Threat Detection via Structured Risk Indicators 将同一用户的日志切成重叠时间窗。第一阶段提取风险指标，第二阶段分类，可检索该用户此前的相似窗口。CERT 最佳配置由 Llama 3.1 8B 提取指标，DeepSeek-R1-Distill-Qwen 32B 分类，并使用检索。

在 CERT r5.2 上，原始数据约 7,990 万条、2,000 名用户。作者仅从 99 名已知恶意用户构窗，抽取 9,571 个窗口，其中 4,410 个为阳性。最佳配置的精确率为 48.55%、召回率为 94.47%、F1 为 64.14%。阳性占比达 46.1%，且正常窗口也来自这批用户；要估算全员部署误报，仍需加入一直正常的员工。 [风险指标论文及表 1、4、5](https://arxiv.org/html/2608.16508v1)

## 3 检测成绩如何随实验口径变化

### FusionITD 提供可复核的时间划分与误报率

Yuan 等 · Cybersecurity，2026 年 2 月 9 日在线发表。FusionITD: enhanced cross-modal insider threat perception framework via behavior-semantic fusion。研究将用户与主机的行为图和邮件、网页的语义证据分别建模。WR-GNN 为行为打分，DeepSeek-V3 辅助检索和判断文本证据，最后用逻辑回归融合。论文使用前 150 天作训练、后 50 天作验证。 [FusionITD 全文及表 5](https://link.springer.com/article/10.1186/s42400-026-00555-w)

| FusionITD 验证集 | ROC-AUC | 真正率 TPR | 误报率 FPR |
| --- | --- | --- | --- |
| CERT r4.2 | 0.9765 | 0.9231 | 0.0142 |
| CERT r5.2 | 0.9816 | 0.9327 | 0.0415 |

表 5 的两个版本上，ROC-AUC 均接近 0.98，但 r5.2 的误报率约为 r4.2 的 2.9 倍。若业务每天面对一万个正常样本，按这两个误报率等比例换算，分别对应约 142 和 415 个误报。这只是解释误报率的算例，真实组织仍需用自己的阈值和流量验证。 [FusionITD 全文及表 5](https://link.springer.com/article/10.1186/s42400-026-00555-w)

### 多 Agent 是否比单模型更会查证

窗口外的 Audit-LLM（2024 年 arXiv）用三个角色拆解任务、构建审计工具并执行查询，两个执行者利用证据交叉核对结论。在 CERT r4.2、r5.2 与 PicoDomain 上的实验为“多 Agent 检测员工”提供了直接对照。可在相同日志和复核预算下，比较单模型、多 Agent 协作各自找到多少真实证据。 [Audit-LLM](https://arxiv.org/abs/2408.08902)

Song 等的 Confront Insider Threat（COLING 2025 年 1 月）在 CERT r6.2 报告 F1 0.8941。DMFI（ICDM 2025 年 11 月 12 日出版）对内容语义与行为序列分别做 LoRA 微调后再融合。两篇均发表于本窗口之前，可分别作微调基线和双视图基线。 [COLING 2025 论文](https://aclanthology.org/2025.coling-main.574/) · [DMFI 正式论文](https://doi.org/10.1109/ICDM65498.2025.00046)

### 从检测到干预

Cyrine Fekih 等的 Learning Insider-Threat Intervention Policies from Offline Logs 发表于 ICML 2026 的 DEMO Workshop。强化学习 Agent 从员工时间窗决定继续观察或介入。五个按用户划分的实验折检出 42% 至 64% 的恶意用户，误报仍高。这里的 Agent 指决策策略，作者使用 DQN、PPO。 [ICML DEMO Workshop 海报](https://icml.cc/virtual/2026/83728)

## 4 用模拟组织构建员工威胁数据

### Morpheus 用多智能体生成日志，再用既有检测器验证

Jiongchi Yu 等 · NDSS 2026。Chimera: Harnessing Multi-Agent LLMs for Automatic Insider Threat Simulation。在科技、金融、医疗三个组织中，每个组织由 20 个员工 Agent 模拟一个月，角色分工、会议和任务执行形成正常活动。研究者配置 15 个威胁场景，将相关活动置于同样的工作环境。ChimeraLog 收集登录、邮件、浏览、文件操作、网络流量、系统日志六类记录。

约 250 亿条记录中，约 20 亿为应用层事件、45 亿为网络包、182 亿为系统日志。检测实验把 CERT r6.2 和 ChimeraLog 映射到按用户、按天聚合的行为特征，再比较 SVM、时序 CNN、GCN 和 DS-IID。原始事件量因此不能当作独立的有标注训练样本数。 [NDSS 正式论文](https://www.ndss-symposium.org/ndss-paper/chimera-harnessing-multi-agent-llms-for-automatic-insider-threat-simulation/) · [NDSS 全文](https://www.ndss-symposium.org/wp-content/uploads/2026-f375-paper.pdf)

| DS-IID 的训练域 | 测试域 | F1 | 解读 |
| --- | --- | --- | --- |
| CERT r6.2 | CERT r6.2 | 0.955 | 同域，论文表 IV |
| Morpheus-Finance | Morpheus-Finance | 0.786 | 同域，论文表 IV |
| CERT r6.2 | Morpheus-Finance | 0.464 | 跨域，论文表 V |
| Morpheus-Finance | CERT r6.2 | 0.739 | 跨域，论文表 V |

两个跨域方向的 F1 相差 0.275。论文按源域和目标域评估，组织、日志分布及样本构成一起变化。仅凭这组差距无法确定究竟是哪种变化导致误报。复现时应保留域标识与目标域阳性率。 [NDSS 全文](https://www.ndss-symposium.org/wp-content/uploads/2026-f375-paper.pdf) · [论文所列项目入口](https://sites.google.com/view/chimerallm) · [原 Chimera 代码](https://github.com/fish98/Chimera)

### OrgForge-IT 用确定性状态验证告警和责任归属

Jeffrey Flynt · arXiv，2026 年 3 月。OrgForge-IT: A Verifiable Synthetic Benchmark for LLM-Based Insider Threat Detection。确定性引擎维护事实，LLM 填充自然语言内容。语料覆盖 51 天、4 个检测场景、3 类威胁和 8 种行为。2,904 条遥测含 106 条信号和 2,798 条噪声，另有干净基线记录。

论文 v1 中，10 个模型有 8 个初筛 F1 同为 0.80，最终判定 F1 却分为 1.00 和 0.80。DeepSeek v3.2 与 Llama 3.3 70B 最终 F1 同为 0.80，基线误报率分别为 0.021 和 0.813。四个设计场景适合复核分诊、归因和误报，跨组织效度仍需单独验证。分数取自论文实验表。 [OrgForge-IT 论文](https://arxiv.org/abs/2603.22499) · [OrgForge-IT 数据](https://huggingface.co/datasets/aeriesec/orgforge-insider-threat)

## 5 当被监测主体是组织内的 AI 账号

### MOLE 直接衡量有限复核预算下能发现多少实际损害

Aashiq Muhamed、Virginia Smith · arXiv，2026 年 9 月。MOLE: Detecting Insider Threats in AI Agents。150 个 AI 操作账号在 9 个有状态服务上工作 30 个工作日。4 个模型生成 8 份语料，覆盖 12 类威胁。作者公开约 2,460 万条审计事件、26.8 万份会话记录和账号日结果标签。作者用服务状态验证是否造成损害。截至检索日，公开记录为 ICLR 2027 投稿。 [MOLE 论文](https://arxiv.org/abs/2609.06966) · [MOLE 数据](https://huggingface.co/datasets/forgelab/mole) · [作者仓库与发布规模](https://github.com/aashiqmuhamed/mole) · [ICLR 2027 投稿记录](https://openreview.net/forum?id=4ho38AY6PT)

在 GPT-5.3 生成的单日任务语料、监测器只能看审计事件的设置下，每天复核排名前 10 的账号，最佳监测器 R@10/day 为 0.533。分母是评估期内发生了已验证损害的账号日总数。这一指标刻画每日复核预算对应的检出能力，CERT 的窗口 F1 则同时受精确率与召回率影响。 [MOLE 论文](https://arxiv.org/abs/2609.06966)

### 三种主会评测设计可以迁移到企业审计

| 研究与数据 | 实验做法及结果 | 可迁移的部分 |
| --- | --- | --- |
| Kale 等<br>ICLR 2026<br>SHADE-Arena、CUA-SHADE-Arena | 监测器读取工具或桌面操作轨迹。只把预警案例交给人工复核，在 FPR=0.01 时，作者报告 TPR 提升 15%。 | 在固定误报率下衡量增加一次人工复核的收益，并记录复核量。 |
| Arike 等<br>ICML 2026<br>BigCodeBench-Sabotage | EaE 先从轨迹选证据片段，再交另一监测器评分。在 GPT-4.1-mini 监测设置下，检出率比次优方法高 16.8 个百分点。 | 让审计员看到触发判定的证据。另测仅凭企业可见日志还能保留多少检出能力。 |
| Storf 等<br>ICML 2026<br>STRIDE、Gloom、Control Arena | 两种构造方法各生成 1,000 条轨迹，以 7,500 条留出的 Control Arena 轨迹检验黑盒监测泛化。优化过度时出现过拟合。 | 用一个环境开发评分规则，冻结后移到另一环境；留出数据应来自独立生成流程。 |

原文题名依次为 Reliable Weak-to-Strong Monitoring of LLM Agents、How does information access affect LLM monitors’ ability to detect sabotage?、Constitutional Black-Box Monitoring for Scheming in LLM Agents。三者的实验单位均是任务轨迹。 [ICLR 会议论文](https://iclr.cc/virtual/2026/poster/10009049) · [EaE 论文](https://icml.cc/virtual/2026/poster/62038) · [ICML 会议论文](https://icml.cc/virtual/2026/poster/65104)

## 6 权限判断和异常定位提供哪些旁证

### 组织权限为合法但少见的行为提供对照

Debdeep Sanyal 等 · EMNLP 2026。OrgAccess: A Benchmark for Role-Based Access Control in Organization Scale LLMs。基准含 70,000 个合成实例、40 类权限。系统需对请求给出完全允许、部分允许或拒绝。简单、中等、困难三档分别含 1、3、5 个同时约束，最难档最佳宏 F1 仅 0.27。对内部威胁研究，岗位授权可解释一次罕见访问；OrgAccess 的权限标签可用于构造合法困难负例。 [OrgAccess 论文](https://aclanthology.org/2026.emnlp-main.1700/)

### 轨迹是否可疑与哪个主体负责需要分别打分

Hanjun Luo 等 · NeurIPS 2025。AgentAuditor: Human-level Safety and Security Evaluation for LLM Agents 用过往案例辅助评审。ASSEBench 有 2,293 条已标注交互、29 个应用场景、15 类风险。模棱两可的案例按严格和宽松两种口径判定。在员工审计中，可沿用双口径记录标签争议，将证据不足保留下来。 [AgentAuditor 论文](https://neurips.cc/virtual/2025/poster/120154) · [作者仓库](https://github.com/Astarojth/AgentAuditor-ASSEBench)

Junjun Pan 等的 XG-Guard 和 Rui Miao 等的 BlindGuard 均发表于 ACL 2026，研究多 Agent 对话中的异常主体。XG-Guard 用双层图做无监督检测与定位。在其论文的链式拓扑、InjecAgent 设置下，XG-Guard 的 Agent 级 AUC 为 99.56%，BlindGuard 为 84.89%。这组结果只支持该设置下的异常节点排序。 [XG-Guard 全文](https://aclanthology.org/2026.acl-long.1407.pdf) · [BlindGuard 论文](https://aclanthology.org/2026.acl-long.1819/)

### 从多条告警还原一次异常活动

Yiru Gong 等的 GARNET（AAAI 2026）将相关告警整理成事件链，作者在六个攻击场景中报告平均减少 80% 的误报。Lior Vaknin 等的 MAStitch（AAMAS 2026）结合局部和全局视角检测多智能体应用异常，作者报告平均 F1 为 0.90。前者的观测单位是安全告警，后者是 Agent 应用运行。 [GARNET 论文](https://doi.org/10.1609/aaai.v40i1.36994) · [MAStitch 论文](https://www.ifaamas.org/Proceedings/aamas2026/pdfs/BMJZ4532.pdf)

## 7 为 Morpheus 选择可比的数据与指标

| 数据与获取入口 | 可看见的证据和标签 | 最适合回答的问题 |
| --- | --- | --- |
| CERT<br>CMU 公共数据 | 合成员工行为和恶意脚本，答案文件标明场景、人员和活动。应记录 r4.2、r5.2 或 r6.2 的具体版本。 | 在固定版本和预测粒度上，规则、统计模型和大模型谁更好？ |
| ChimeraLog<br>NDSS 项目与代码入口 | 组织互动及多模态日志，实验用用户日特征。海量系统调用仍来自有限场景。 | 同一检测器换组织后损失多少？增加邮件、文件或流量各带来多少信息？ |
| OrgForge-IT<br>公开数据卡 | 跨天遥测、自然语言材料、独立真值和干净基线。可以核对模型把风险归给了谁。 | 初筛正确之后，能否正确解释事件并避免归咎受害账号？ |
| MOLE<br>公开数据卡 | AI 账号的审计事件、会话、服务状态和账号日标签。审计视图与更完整轨迹可分开评。 | 每天只能复核 K 个账号时，能发现多少已造成的损害？ |

[CERT 数据与标注](https://doi.org/10.1184/R1/12841247.v1) · [论文所列项目入口](https://sites.google.com/view/chimerallm) · [原 Chimera 代码](https://github.com/fish98/Chimera) · [OrgForge-IT 数据](https://huggingface.co/datasets/aeriesec/orgforge-insider-threat) · [MOLE 数据](https://huggingface.co/datasets/forgelab/mole)

### 建议采用的对照实验

① 固定输入。以用户日为共同单位，先在 CERT r6.2 和 ChimeraLog 上保留可对齐的登录、文件、邮件等特征，再单独加入 Morpheus 的额外模态。第一组隔离检测方法差异，第二组测额外证据的贡献。

② 固定划分和预算。报告同域与跨组织两组结果，按用户隔离训练和测试，按时间构造历史，避免相邻重叠窗口泄漏。保留全量正常员工及其用户日，按真实测试占比报告 PR-AUC、阳性 F1、每千正常用户日误报数和每天前 K 个告警的召回率。

③ 分别核验告警、归因和结果。为每个阳性用户日保存可观察的证据记录、授权状态与结果标签。按当前账号、实际责任主体和是否发生损害分别评分。可用同岗位夜间获批访问作为困难负例，检验模型是否只学会识别“非工作时间”。以上三步为建议实验。文中实验分数均取自原作者报告。

## 8 检索范围与阅读依据

以会议实际举办时间确定正式论文是否入窗，期刊及预印本记录公开日期。直接研究须同时涉及组织内部账号、LLM 或 Agent，以及带行为证据的检测或数据构建。按题名和摘要筛选相关候选，再按全文、数据卡或官方摘要核实任务、模型角色和指标。

| 目录及读取范围 | 命中情况和可核验边界 |
| --- | --- |
| NeurIPS 2025、ICLR 与 ICML 2026 | 海报目录分别有 5,858、5,468、6,628 个唯一题名，共 17,954 个，17,953 个有摘要。检出多项 AI 轨迹监控研究。 |
| ACL、EMNLP、AAAI、IJCAI 2026 | ACL 主会长短文 2,296 篇，EMNLP 主会 2,704 篇。AAAI 第 40 卷 4,920 项含多轨记录，IJCAI 全轨 973 篇。AAAI 命中的 Cates 等研究内部威胁欺骗建模。 |
| WWW、KDD、AAMAS 2026 | WWW 研究论文目录、KDD 两轮接收目录和 AAMAS 论文集以题名筛选。WWW 命中 Insight-LLM，AAMAS 命中多 Agent 异常检测。 |
| NDSS、ICASSP、期刊和预印本 | ICASSP 为信号处理旗舰会，NDSS 为网络安全旗舰会，均作领域补充。按题名、作者和引用追踪会议论文、期刊及预印本。 |

关键词包括 insider threat、insider risk、malicious employee、UEBA、CERT、user behavior analytics、audit log，并扩展至 agent monitoring、sabotage、data exfiltration、role-based access control。目录级筛选可能遗漏仅在正文中使用 CERT 或间接描述员工数据的论文。NeurIPS 2026 主会在 12 月，超出本次会期窗口。

[NeurIPS 2025](https://neurips.cc/virtual/2025/loc/san-diego/papers.html) · [ICLR 2026](https://iclr.cc/virtual/2026/papers.html) · [ICML 2026](https://icml.cc/virtual/2026/papers.html) · [NeurIPS 2026 会期](https://neurips.cc/Conferences/2026) · [ACL 长文](https://aclanthology.org/2026.acl-long/) · [ACL 短文](https://aclanthology.org/2026.acl-short/) · [EMNLP](https://aclanthology.org/2026.emnlp-main/) · [AAAI 会刊](https://ojs.aaai.org/index.php/AAAI/issue/archive) · [IJCAI](https://www.ijcai.org/proceedings/2026/) · [WWW 研究论文](https://www2026.thewebconf.org/accepted/research-tracks.html) · [KDD 两轮目录](https://kdd2026.kdd.org/papers/) · [AAMAS 论文集](https://www.ifaamas.org/Proceedings/aamas2026/forms/contents.htm) · [AAAI 内部威胁建模论文](https://doi.org/10.1609/aaai.v40i35.40173)

### 来源使用说明

会议目录和 DOI 用于核定发表身份，实验数字优先取正式全文及指定表格。Insight-LLM 的编码器、基座比较、数据规模和绝对结果来自 Semantic Scholar 对出版论文图表的公开抽取图像，ACM 页面在本次检索环境中未提供可直接下载的 PDF。LLMBA 的细节仅采用可核验的公开摘要。Morpheus 项目入口来自 NDSS 全文参考文献 [26]，全量日志包未逐项下载核验。页内链接指向论文、数据卡或会议目录。 [可读摘要](https://api.openalex.org/works/https://doi.org/10.1145/3774904.3792398) · [ICASSP 论文](https://doi.org/10.1109/ICASSP55912.2026.11463924) · [NDSS 全文](https://www.ndss-symposium.org/wp-content/uploads/2026-f375-paper.pdf)
