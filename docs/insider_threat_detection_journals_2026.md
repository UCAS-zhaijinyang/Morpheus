# 近一年内部威胁检测期刊论文调研

检索日期为 2026 年 11 月 20 日，主要检索窗口为 2025 年 11 月 20 日至 2026 年 11 月 20 日。论文需要已经有 DOI，并且能够在出版社页面、Crossref 或作者正式存档中核对题名、期刊和方法信息。

## 口径

IEEE Transactions on Information Forensics and Security（TIFS）按中国计算机学会网络与信息安全目录属于 A 类安全旗舰期刊。窗口内直接以内部威胁检测为主题、且新增的方法论文，我核到 TIFS 的 ISFL-AE。TIFS 的 LLMBA 是此前已经讨论过的同方向对照，因此在本文只作定位，不重复计数。IEEE TAI、Expert Systems with Applications、Cybersecurity、Wiley Security and Privacy 等论文作为高水平或专题期刊补充，不统称为 CCF A。CCF 目录入口见 [CCF 网络与信息安全目录](https://www.ccf.org.cn/Academic_Evaluation/NIS/)。

## 结论先看

- 最适合作为 Morpheus 检测器对照的新方法是 **ISFL-AE**。它把员工角色、权限等个体属性注入自编码器，并在 CERT r4.2/r6.2 上验证轻量化部署，适合研究“个体基线”和计算开销。
- 最适合研究结构和时间依赖的是 **GCN + Bi-LSTM**。它同时构造规则显式图和相似性隐式图，在 CERT r5.2/r6.2 上报告了 AUC、检测率和误报率。
- 最适合研究多智能体检测流程的是 **MARS-ITD**。它把并行异常初筛和跨日志调查分成两个阶段，在 CERT r4.2 的用户会话粒度上报告了召回率、准确率和 FPR。
- 最新的应用型工作开始把评测从离线分类扩展到文件系统响应、蜜标记和隐私攻击。它们更接近部署验证，数据集常常不是 CERT，需要与 Morpheus 的跨组织实验分开比较。

## 严格顶刊与直接方法

### ISFL-AE

**Yujun Kim、Young-Gab Kim，ISFL-AE: Insider-Specific Feature Learning Autoencoder for Lightweight Insider Threat Detection，IEEE Transactions on Information Forensics and Security，2026，vol. 21，pp. 1638–1653。** DOI 为 [10.1109/TIFS.2026.3659000](https://doi.org/10.1109/TIFS.2026.3659000)，IEEE Xplore 记录为 [arnumber 11367073](https://ieeexplore.ieee.org/document/11367073/)。

- **模型。** 以重构式自编码器为基础，用员工角色、权限级别等 insider-specific 属性调节特征学习，使不同员工拥有条件化的正常行为表示。论文强调参数量与传统 AE 相同，处理速度相当。
- **数据。** CERT r4.2 和 CERT r6.2。
- **结果。** 摘要给出“同速率下显著提高检测准确率”，但没有给出可直接复核的绝对 F1、AUC 或 FPR。报告时不应把摘要中的定性表述换算成具体数值。
- **对 Morpheus 的启发。** Morpheus 可以把组织、角色和权限作为条件变量，比较一个全局 AE、用户独立 AE 与 ISFL-AE。在 CERT 到模拟组织的跨域实验中，还可以检验个体条件是否缓解分布偏移。

### LLMBA 作为已知顶刊对照

**Senming Yan 等，LLMBA: Efficient Behavior Analytics via Large Pretrained Models in Zero Trust Networks，IEEE TIFS，2026，vol. 21，pp. 2403–2415。** DOI 为 [10.1109/TIFS.2026.3666459](https://doi.org/10.1109/TIFS.2026.3666459)。论文采用多级行为编码、自监督微调和知识蒸馏，把大模型压缩为运行时更轻的学生模型，并在 CERT 上评测。公开摘要没有给出具体基座 checkpoint、样本粒度和可对齐的绝对分数，因此适合作为方法路线对照，不宜补猜模型名称或数值。

## 2026 年高水平或专题期刊补充

### 双图 GCN 与 Bi-LSTM

**Rahul Yumlembam 等，Insider Threat Detection Using GCN and Bi-LSTM With Explicit and Implicit Graph Representations，IEEE Transactions on Artificial Intelligence，vol. 7，issue 7，pp. 3872–3883，2026。** DOI 为 [10.1109/TAI.2025.3647418](https://doi.org/10.1109/TAI.2025.3647418)，作者接受稿为 [Accepted Manuscript](https://research.tees.ac.uk/ws/files/113753430/Accepted_Manuscript_IEEE_TAI.pdf)。

- **模型。** 一条图由预定义规则建立，另一条图通过特征相似性和 Gumbel-Softmax 学习。两张图分别经过 GCN，拼接后用注意力筛选关键特征，再用 Bi-LSTM 建模时间依赖，概率低于阈值的活动被标为异常。
- **数据。** CERT r5.2 和 r6.2，特征来自 logon、file、email、device、HTTP 和 psychometric 日志。接受稿说明了下一活动掩码、过采样和训练测试流程。
- **结果。** r5.2 的 AUC 为 98.62%（0.9862），检测率为 100%，FPR 原表记作 0.05。r6.2 的 AUC 为 88.48%，检测率为 80.15%，FPR 原表记作 0.15。FPR 的量纲在摘要和表格中没有完全说明，复现时应按原文表格核对后统一。
- **对 Morpheus 的启发。** 该方法适合用来检查 Morpheus 是否保留了员工—资源—行为关系，以及模拟日志在关系结构和时间顺序上是否接近 CERT。

### MARS-ITD 多智能体检测与调查

**Kai Cheng 等，Multi-Agent Real-Time Detection of Insider Threats via Collaborative Reasoning，Wiley Security and Privacy，vol. 9，issue 5，2026-08-04 online。** DOI 为 [10.1002/spy2.70243](https://doi.org/10.1002/spy2.70243)。

- **模型。** MARS-ITD 将并行多智能体异常初筛和协作调查分成两个框架。初筛阶段并行处理异常日志，调查阶段跨日志类型关联证据并还原完整威胁场景。摘要没有指定单一的基础 LLM checkpoint。
- **数据和粒度。** CERT r4.2，用户会话级检测。论文同时比较 GNN 基线和 LLM 微调方法 ITDLM。
- **结果。** Recall 94.44%，Accuracy 95.42%，FPR 4.58%。同文 GNN 基线的 FPR 为 8.25%–14.88%。消融实验显示调查阶段降低了误报并提高了召回。
- **对 Morpheus 的启发。** Morpheus 的多模态日志可以按“并行初筛—跨源调查—证据链输出”重做评测，特别适合比较单一分类器和调查型 Agent 的差别。

### MSGL 多尺度群组学习

**Mengxue Pang 等，MSGL: A multi-scale group learning model for insider threat detection，Expert Systems with Applications，vol. 323，132379，2026。** DOI 为 [10.1016/j.eswa.2026.132379](https://doi.org/10.1016/j.eswa.2026.132379)，出版社页面为 [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0957417426012923)。

- **模型。** 加权注意力在不同时间粒度提取行为特征，结构感知 GNN 建模员工群组依赖，group-sparsity 正则抑制伪关联，individual sparse attention 分离群体共性与个人偏离。
- **数据。** CERT r4.2 和 r5.2。
- **结果。** 两个数据集上的准确率分别为 96.28% 和 97.41%。这里报告的是 Accuracy，不是 F1。CERT 类别不平衡时应同时报告 PR-AUC、召回率和 FPR。
- **对 Morpheus 的启发。** 可把组织中的部门、项目组和协作关系显式加入图，检验群体共同行为是否会掩盖个人异常。

### BTITD 行为—时间双流网络

**Chen Zhang 等，BTITD: an insider threat detection method based on behavior-timestamp dual-stream network，Cybersecurity，2026-06-22 online。** DOI 为 [10.1186/s42400-026-00591-6](https://link.springer.com/article/10.1186/s42400-026-00591-6)。

- **模型。** 行为流先做 Fourier 变换，再按关键周期折叠为二维张量并用 2D CNN 提取多尺度周期模式。绝对时间流用 Bi-LSTM 建模长程依赖，最后用注意力融合两路表示。
- **数据。** CERT r4.2。
- **结果。** 二分类 F1 为 97.56%，多分类 macro-F1 为 94.66%。
- **对 Morpheus 的启发。** Morpheus 生成器应保留绝对时间戳和周期性，而不是只保留按天聚合的行为计数。多类威胁场景也应单独报告 macro-F1。

### TL-CsLeNet 与特征工程消融

**Hina Naaz、Reema Ajmera，AI-driven user behavior analytics for cybersecurity enhancement through anomaly detection，Discover Computing，vol. 29，2026-11-16。** DOI 为 [10.1007/s10791-026-10827-1](https://doi.org/10.1007/s10791-026-10827-1)。

- **模型。** TL-CsLeNet 是定制的一维卷积检测器，输入经过 SASZ 归一化、较高阶统计特征、直接归一化特征和互信息特征构造，再经 Information Gain 选择。网络使用卷积核宽度 1、3、7 的三条分支，并结合金字塔池化、混合池化、SiLU 和批归一化。最佳配置实际不使用迁移学习。
- **数据。** 公开 UEBA 数据集的 `train_data.csv`，528,690 条事件、151 名用户、7 个部门，异常率 14.25%。作者按训练规模和随机种子重复评估，数据不是 CERT。
- **结果。** 在四种训练划分和三个随机种子的平均结果上，Accuracy 为 91.76%，Precision 为 0.7421，PR-AUC 为 0.7803。80% 训练划分的 PR-AUC 为 0.7893，F1 为 0.7003，Accuracy 为 0.9195。去掉全部特征工程时 PR-AUC 下降 0.22，只去掉 HOS 特征时下降 0.18。
- **对 Morpheus 的启发。** 该文说明特征工程和数据切分可能比网络结构更影响结果。Morpheus 应把日志窗口、特征构造、训练比例和随机种子作为可复现实验变量。

### VAE 与 Transformer Autoencoder 的隐私和漂移评测

**Fatmah Bamashmoos，Adaptive Privacy-Preserving Insider Threat Detection Using Generative Sequence Models，Future Internet，18(1)，11，2025-12-26。** DOI 为 [10.3390/fi18010011](https://doi.org/10.3390/fi18010011)。

- **模型。** 比较 VAE 和 Transformer Autoencoder，从顺序用户事件中学习个性化行为基线。自适应更新处理冷启动和概念漂移，隐空间设计用来降低数据泄露风险。
- **数据。** CERT v5.2。
- **结果。** Transformer Autoencoder 的 F1 为 0.66，AUPRC 为 0.59。论文还进行了 membership inference 和 reconstruction attack 评测。
- **对 Morpheus 的启发。** 除了检测率，跨组织模拟还可以增加概念漂移、成员推断和重构攻击，观察生成数据是否泄露员工身份或威胁标签。

### ISAVNS 优化的 NLP 加 XGBoost

**Tamara Zivkovic 等，Applying metaheuristic optimization for insider-threat detection using natural language processing，International Journal of Data Science and Analytics，2026-02-17 online。** DOI 为 [10.1007/s41060-025-00996-5](https://doi.org/10.1007/s41060-025-00996-5)。

- **模型。** 将 HTTP 活动日志转为 TF-IDF 或 Word2Vec 表示，用 XGBoost 分类，并用 iteration stagnation-aware variable neighborhood search（ISAVNS）优化超参数。
- **数据。** 摘要只说明使用公开内部威胁数据集，没有列出数据集版本。与 CERT 版本的直接对应关系需要阅读全文后再写入复现实验表。
- **结果。** TF-IDF 配置 Accuracy 为 97.63%，Word2Vec 配置 Accuracy 为 97.71%。摘要没有给出 F1、AUPRC 或 FPR。
- **对 Morpheus 的启发。** 它提供了轻量文本行为基线，可用来测试 Morpheus 的 HTTP 语义是否已经足以支撑检测，而无需先引入图网络或 LLM。

### SENTINEL 特权访问场景

**E. Yilmaz、Ozgu Can、M. Kantarcioglu，SENTINEL: Siamese-Based Few-Shot Learning for Explainable Insider Threat Detection，IEEE Access，2026。** DOI 为 [10.1109/ACCESS.2026.3747255](https://doi.org/10.1109/ACCESS.2026.3747255)。

- **模型。** 从 Privileged Access Management（PAM）的数据库访问和会话日志提取上下文与操作特征，为 SQL 活动加入 Data Sensitivity 和 Operation Criticality 分数。Siamese Network 做 few-shot 异常检测，SHAP 解释单条预测，AHP 风险评分量化严重性。
- **数据。** 两个真实 PAM 数据集，加入点异常、上下文异常和集体异常。摘要未公开数据集名称。
- **结果。** 5-fold 交叉验证中，Dataset-1 的 Accuracy、Precision、Recall、F1、ROC-AUC 为 99.81%、97.97%、96.49%、97.23%、98.21%。Dataset-2 为 99.76%、97.50%、95.28%、96.38%、97.95%。论文还做了 10-fold 验证。
- **对 Morpheus 的启发。** 该文适合补充“少标签、特权账号、可解释风险分数”实验，但其 PAM 日志分布与 CERT 员工活动并不等价。

### 蜜文件和蜜标记的主动防御

**Licia Pia Zichella 等，Active Defense and Deception Technology Against Insider Threats: A Serverless and Cryptographically Verifiable Framework，Informatics，13(11)，196，2026-11-16。** DOI 为 [10.3390/informatics13110196](https://doi.org/10.3390/informatics13110196)。

- **方法。** 在云环境中部署动态 honeyfiles、honeytokens 和 PDF、DOCX、XLSX 多格式 web beacons，结合 PAdES 数字签名做归因，并在触发后自动撤销 IAM 权限。
- **评测环境。** AWS 的 LocalStack 和 Docker 仿真环境，不是 CERT 或真实企业数据集。实验覆盖 500 个正常流量事件和建模的恶意行为模式。
- **结果。** 自动响应到发出 IAM 撤销请求的延迟约 2.16 秒，正常事件 FPR 为 0，建模恶意行为召回率为 100%。
- **对 Morpheus 的启发。** 该方法可以作为检测后的响应层，与 Morpheus 的日志生成器连接，用来评估告警到隔离之间的延迟与误触发代价。

## 和 Morpheus 的评测协议怎么对齐

| 维度 | 期刊论文中的常见做法 | Morpheus 适合增加的对照 |
| --- | --- | --- |
| 样本单位 | 事件、用户日、用户会话并存 | 明确区分 event、user-day、session、user 四种单位，避免把窗口数当员工数 |
| 数据集 | CERT r4.2、r5.2、r6.2 仍占主流 | 保留 CERT 同域结果，再做 CERT→模拟组织和模拟组织→CERT |
| 指标 | Accuracy、F1、AUC、FPR、AUPRC 混用 | 主表固定 F1、AUPRC、TPR/Recall、FPR，并报告恶意用户级召回 |
| 时间信息 | GCN-BiLSTM、BTITD 明确使用时间顺序或时间戳 | 不要只发布按天计数，保留绝对时间、周期和跨日志时间对齐 |
| 结构信息 | MSGL 用群组图，双图 GCN 用规则图和相似性图 | 给员工—部门—资源—行为构图，做显式关系和隐式关系消融 |
| 部署约束 | ISFL-AE、LLMBA 关注参数量和运行时，主动防御论文关注响应延迟 | 增加吞吐、显存、每窗口推理时间、告警到响应时间 |
| 可解释性和隐私 | SENTINEL 用 SHAP/AHP，Future Internet 做成员推断和重构攻击 | 同时输出证据链、风险分数和隐私攻击结果 |

## 选择建议

### 面向 Morpheus 主实验的开源方法筛选

2026-11-23 对候选方法的官方代码入口进行了复核。Insight-LLM 和 MARS-ITD 仍未找到可核验的官方实现，不能作为需要完整复现的主实验方法。结构化风险指标方法的论文和开放权重模型可访问，但未找到作者维护的检测代码仓库，也不纳入主实验。

MOLE 是当前最符合主实验约束的开源方法。其论文发表于 2026 年预印本，代码仓库采用 Apache-2.0，提供账号日回放、审计事件适配、LLM 语义监测器、递归 Agent 监测器、预算式级联监测器和评测脚本。Morpheus 主实验从同一仓库固定两个监测器配置。**MOLE-Cascade** 先用低成本筛选器选择需要语义审查的账号日，**MOLE-RLM** 使用递归式 Agent 访问当前轨迹和历史证据后输出怀疑分数。两者都适合映射到 CERT user-day 和 Morpheus employee-day。

因此，当前主实验使用 **MOLE-Cascade 和 MOLE-RLM**。ISFL-AE、双图 GCN-BiLSTM 和 BTITD 保留为后续非大模型基线候选，不与主实验的 Agent 方法混在同一张核心表中。

代码仓库为 [MOLE](https://github.com/aashiqmuhamed/mole)，论文为 [arXiv:2609.06966](https://arxiv.org/abs/2609.06966)，数据为 [Hugging Face forgelab/mole](https://huggingface.co/datasets/forgelab/mole)。

本清单没有把“内部威胁”题名之外的通用网络异常、APT provenance 或防御博弈论文列为直接检测器。也没有把普通会议、预印本和综述当作正式期刊方法论文。
