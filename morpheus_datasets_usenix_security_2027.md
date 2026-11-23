# 4 Morpheus-Datasets

Morpheus-Datasets models insider threats in enterprise workflows where employees delegate work to AI agents. A single routine action, such as reading a project document or sending a report, may appear in both benign and threat traces. The security distinction depends on whose authority enabled the action, which business purpose authorized it, and what happened to the data or resource. We use these distinctions to define threat cases, choose organizational settings, and specify the evidence needed to label a trace.

## 4.1 Modeling Agent-Mediated Insider Threats

We start from CISA’s definition of insider threat, in which a person’s authorized access or organizational knowledge can contribute to harm [1]. We retain Chimera’s practice of embedding threat activity in ordinary work and using the 5W1H taxonomy to connect actors, objectives, timing, settings, motivations, and actions to observable evidence [2]. In Morpheus, the scenario specification represents the initiating employee, the acting agent, the source of the input or procedure, and the affected resource as distinct elements and records the delegation that connects the employee to the agent. A single action can therefore be assessed against the authority granted for that task.

We next define what the organization permits in the underlying task. Following attribute-based access control and work on purpose restrictions, we describe authorization in terms of the acting party, the resource, the operation, and the circumstances of use [3, 4]. For delegated work, the relevant circumstances include the approved task purpose, the scope and duration of the delegation, and the permitted recipients. For a reused procedure, they also include the context in which the procedure was created and the context in which it is applied. The scenario definitions encode each boundary alongside the observable evidence needed to assess it, such as the approved recipient and the recorded destination of a disclosure.

Three threat families follow from this progression. In **AI-mediated data-boundary abuse (T1)**, an employee has legitimate access to task-relevant information, and the security question is whether the agent’s use or disclosure of that information remains within the approved purpose and destination. Generative AI risk guidance and tool-use benchmarks motivate tracing the source, the agent action, and the resulting disclosure [5, 6]. In **cross-department workflow abuse (T2)**, individually authorized handoffs can produce a combined artifact whose use exceeds the project’s approval. The label therefore depends on the full sequence of handoffs and the final use. This extends the user–resource context emphasized by Facade to the authorization of a composed workflow [7]. In **skill or memory contamination (T3)**, a procedure saved in one context influences a later action under different permissions. The evidence ties the reused procedure to its origin and to the resulting action. The design draws on documented risks in reusable agent skills [8].

For each threat case, the protocol pairs an authorized workflow with an intervention that varies one policy-relevant condition, such as the approved recipient, the validity of a delegation, or the scope of a reused procedure. The employee, task, initial schedule, and other starting conditions are held fixed within a pair. A completed violation requires evidence of a policy breach and an observed effect in the simulated environment. Blocked attempts are recorded separately. The detector’s input excludes the intervention marker and the final adjudication.

## 4.2 Selection of Organizational Settings

Following Chimera’s use of organizational settings with different work and access patterns [2], we select three settings that give the same threat families different security contexts. All three involve employee roles, shared resources, and delegated work. Customer and service boundaries matter most in the internet setting, documented approvals in the financial setting, and artifact provenance in the AI development setting.

**Internet software company.** We model a provider of online business software whose support, engineering, and reliability teams collaborate on customer incidents. Google’s site reliability engineering guidance describes a workflow in which teams jointly prepare and review incident reports, share findings, and restrict access to information that can identify users [9]. This setting supplies a benign reason to move information between teams and tools while retaining a clear tenant boundary. It tests whether a detector can distinguish authorized collaboration on an incident from disclosure outside the approved audience, even when both traces contain similar reads and updates.

**Financial institution.** We model a securities firm with research, risk, operations, and compliance functions. FINRA’s rules on supervision and records provide concrete precedents for documented review and retention in a member firm [10, 11]. A routine risk review can legitimately combine information held by several departments, and its authorization can depend on the project, reviewer, and duration of approval. This setting makes it possible to test whether a detector can identify a violation in the combined workflow when each individual access has a plausible business explanation.

**AI model development company.** We model a company whose workflow spans data preparation, model evaluation, and release review. NIST’s secure development profile for generative AI grounds the use of provenance and integrity checks for data and model artifacts [12]. Here, the approved use of an evaluation artifact or reusable procedure can depend on the experiment and artifact version. Repeated evaluations and releases provide ordinary occasions to reuse procedures, so the setting tests whether a detector can identify reuse that causes a policy violation after the authorized context changes.

## 4.3 Data Generation Configuration

The planned generation protocol uses DeepSeek Harness (`deepseek-harness`) and defines one simulated organization per setting. Each organization has 100 simulated employees and a horizon of 50 workdays, arranged as ten Monday–Friday weeks. This gives a nominal capacity of 5,000 employee-days per organization and 15,000 across the three settings, before counting additional traces from matched interventions. An employee-day groups one employee’s recorded activity on one simulated workday. Organization goals and employee roles establish the routine schedules in which the threat cases are evaluated.

## References

[1] Cybersecurity and Infrastructure Security Agency. *Insider Threat Mitigation*. [CISA](https://www.cisa.gov/topics/physical-security/insider-threat-mitigation)

[2] Jiongchi Yu, Xiaofei Xie, Qiang Hu, Yuhan Ma, and Ziming Zhao. “Chimera: Harnessing Multi-Agent LLMs for Automatic Insider Threat Simulation.” *Network and Distributed System Security Symposium*, 2026. [NDSS](https://www.ndss-symposium.org/ndss-paper/chimera-harnessing-multi-agent-llms-for-automatic-insider-threat-simulation/)

[3] Vincent C. Hu et al. *Guide to Attribute Based Access Control (ABAC) Definition and Considerations*. NIST SP 800-162, updated 2019. [NIST](https://csrc.nist.gov/pubs/sp/800/162/upd2/final)

[4] Michael Carl Tschantz, Anupam Datta, and Jeannette M. Wing. “Formalizing and Enforcing Purpose Restrictions in Privacy Policies.” *IEEE Symposium on Security and Privacy*, 2012. [DOI](https://doi.org/10.1109/SP.2012.21)

[5] Chloe Autio et al. *Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile*. NIST AI 600-1, 2024. [DOI](https://doi.org/10.6028/NIST.AI.600-1)

[6] Edoardo Debenedetti et al. “AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents.” *Advances in Neural Information Processing Systems*, 37, 2024. [NeurIPS](https://proceedings.neurips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html)

[7] Alex Kantchelian et al. “Facade: High-Precision Insider Threat Detection Using Deep Contextual Anomaly Detection.” *35th USENIX Security Symposium*, 2026. [USENIX](https://www.usenix.org/conference/usenixsecurity26/presentation/kantchelian)

[8] Yi Liu et al. “Do Not Mention This to the User: Detecting and Understanding Malicious Agent Skills in the Wild.” *35th USENIX Security Symposium*, 2026. [USENIX](https://www.usenix.org/conference/usenixsecurity26/presentation/liu-yi)

[9] John Lunney and Sue Lueder. “Postmortem Culture: Learning from Failure.” In *Site Reliability Engineering*, 2016. [Google SRE](https://sre.google/sre-book/postmortem-culture/)

[10] Financial Industry Regulatory Authority. *Rule 3110. Supervision*. [FINRA](https://www.finra.org/rules-guidance/rulebooks/finra-rules/3110)

[11] Financial Industry Regulatory Authority. *Rule 4511. General Requirements*. [FINRA](https://www.finra.org/rules-guidance/rulebooks/finra-rules/4511)

[12] Harold Booth, Murugiah Souppaya, Apostol Vassilev, Michael Ogata, Martin Stanley, and Karen Scarfone. *Secure Software Development Practices for Generative AI and Dual-Use Foundation Models: An SSDF Community Profile*. NIST SP 800-218A, 2024. [DOI](https://doi.org/10.6028/NIST.SP.800-218A)

---

# 4 Morpheus-Datasets 数据集

Morpheus-Datasets 对企业员工将任务委托给 AI 智能体时产生的内部威胁进行建模。读取项目文档、发送报告等常规操作可以同时出现在正常轨迹和威胁轨迹中。判断操作的安全性，需要知道它由谁的权限支持、获批的业务目的是什么，以及相关数据或资源实际发生了什么变化。我们据此定义威胁案例、选择组织场景，并规定标注轨迹所需的证据。

## 4.1 智能体介导的内部威胁建模

我们从 CISA 对内部威胁的定义出发。内部人员拥有的授权访问权限或组织知识可能被用于造成损害 [1]。我们沿用 Chimera 将威胁活动嵌入日常工作的做法，并使用 5W1H 方法将参与者、目标、时机、环境、动机和行为与可观察证据关联起来 [2]。Morpheus 的场景规范分别记录发起任务的员工、执行操作的智能体、输入或流程的来源、受影响的资源，以及员工与智能体之间的委托关系。这样就可以依据具体任务的授权判定一次操作是否合规。

接下来，我们界定组织在具体业务任务中允许哪些操作。参考基于属性的访问控制及用途限制研究，我们从行为主体、资源、操作和使用情境描述授权 [3, 4]。在委托任务中，使用情境包括获批任务目的、委托的范围和有效期，以及允许接收结果的对象。若任务涉及流程复用，还需记录流程产生时的授权情境及本次使用时的情境。场景定义同时记录安全边界与判定所需的可观察证据，例如获批接收者和实际披露的目的地。

据此构建三类威胁。**AI 介导的数据边界滥用（T1）**始于员工对任务相关信息的合法访问，关注智能体使用或披露信息时是否符合获批用途和接收范围。生成式 AI 风险指南和工具调用基准为关联记录源数据、智能体操作与实际披露结果提供依据 [5, 6]。在**跨部门流程滥用（T2）**中，各次交接都可能获批，但聚合产物的用途可能超出项目审批范围。判定需要检查完整的交接链和产物的最终用途。这将 Facade 所强调的用户与资源上下文延伸到对组合工作流的授权判断 [7]。在**技能或记忆污染（T3）**中，早先保存的流程在权限情境发生变化后影响了后续操作。判定需要关联流程来源、当前复用行为和实际结果。该场景参考了关于可复用智能体技能风险的实证研究 [8]。

配对协议为每个威胁案例设置一条获批的工作轨迹，并改变一个与策略相关的条件，例如获批接收者、委托是否仍然有效，或被复用流程的适用范围。配对中的员工、任务、初始日程及其他起始条件保持一致。判为已发生的违规须同时具有违反策略的证据和模拟环境中可观察到的效果。被阻止的尝试单独记录，干预标记和最终裁定仅用于标注。

## 4.2 组织场景选择

Chimera 通过不同组织的工作流程和访问模式形成对照 [2]。沿用这一原则，我们选择三种组织，在不同的安全约束下考察同一组威胁机制。三者均包含员工角色、共享资源和任务委托。在互联网场景中，客户与服务范围是主要约束。在金融场景中，重点是有记录可查的审批。在 AI 研发场景中，重点是产物的来源和版本。

**互联网软件公司。** 我们模拟一家面向企业客户的在线软件服务商，由客户支持、工程及站点可靠性团队协同处理客户事件。Google SRE 指南描述了团队共同撰写和审阅复盘报告、共享经验并限制可识别用户信息访问的实践 [9]。因此，跨团队和跨工具传递信息本身可以是正常的业务活动，同时仍受租户范围约束。即使两条轨迹包含相似的读取和更新记录，该场景也能考察检测器是否区分获批的事件协作与超出许可范围的披露。

**金融机构。** 我们模拟一家承担研究、风险、运营和合规职能的证券机构。FINRA 对会员机构的监督和记录保存要求为书面复核及留存流程提供了实际依据 [10, 11]。例行风险审查可以合法汇集多个部门持有的信息，授权则可能取决于项目、审查人和审批有效期。该场景考察的是，当每次访问都有合理的业务解释时，检测器能否识别在整体工作流程中发生的越界。

**AI 模型研发公司。** 我们模拟一家开展数据准备、模型评测和发布审查的公司。NIST 的生成式 AI 安全开发规范为数据和模型产物的来源及完整性检查提供依据 [12]。评测产物或可复用流程的获批用途可能取决于实验环境和产物版本。重复评测和发布本身就需要复用流程，因此该场景可以检验检测器能否识别因授权情境变化而造成违规的流程复用。

## 4.3 数据生成配置

计划使用 DeepSeek Harness（`deepseek-harness`），每个场景对应一个模拟组织。每家组织设置 100 名模拟员工和 50 个模拟工作日，按周一至周五安排为 10 个工作周。每家组织的计划规模为 5,000 个员工日，三个场景合计 15,000 个员工日。配对干预产生的额外轨迹另计。一个员工日汇集一名员工在一个模拟工作日中的活动记录。组织目标和岗位职责决定常规工作日程，威胁案例在这些日程所提供的业务情境下评估。

## 参考文献

[1] Cybersecurity and Infrastructure Security Agency. *Insider Threat Mitigation*. [CISA](https://www.cisa.gov/topics/physical-security/insider-threat-mitigation)

[2] Jiongchi Yu, Xiaofei Xie, Qiang Hu, Yuhan Ma, and Ziming Zhao. “Chimera: Harnessing Multi-Agent LLMs for Automatic Insider Threat Simulation.” *Network and Distributed System Security Symposium*, 2026. [NDSS](https://www.ndss-symposium.org/ndss-paper/chimera-harnessing-multi-agent-llms-for-automatic-insider-threat-simulation/)

[3] Vincent C. Hu et al. *Guide to Attribute Based Access Control (ABAC) Definition and Considerations*. NIST SP 800-162, updated 2019. [NIST](https://csrc.nist.gov/pubs/sp/800/162/upd2/final)

[4] Michael Carl Tschantz, Anupam Datta, and Jeannette M. Wing. “Formalizing and Enforcing Purpose Restrictions in Privacy Policies.” *IEEE Symposium on Security and Privacy*, 2012. [DOI](https://doi.org/10.1109/SP.2012.21)

[5] Chloe Autio et al. *Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile*. NIST AI 600-1, 2024. [DOI](https://doi.org/10.6028/NIST.AI.600-1)

[6] Edoardo Debenedetti et al. “AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents.” *Advances in Neural Information Processing Systems*, 37, 2024. [NeurIPS](https://proceedings.neurips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html)

[7] Alex Kantchelian et al. “Facade: High-Precision Insider Threat Detection Using Deep Contextual Anomaly Detection.” *35th USENIX Security Symposium*, 2026. [USENIX](https://www.usenix.org/conference/usenixsecurity26/presentation/kantchelian)

[8] Yi Liu et al. “Do Not Mention This to the User: Detecting and Understanding Malicious Agent Skills in the Wild.” *35th USENIX Security Symposium*, 2026. [USENIX](https://www.usenix.org/conference/usenixsecurity26/presentation/liu-yi)

[9] John Lunney and Sue Lueder. “Postmortem Culture: Learning from Failure.” In *Site Reliability Engineering*, 2016. [Google SRE](https://sre.google/sre-book/postmortem-culture/)

[10] Financial Industry Regulatory Authority. *Rule 3110. Supervision*. [FINRA](https://www.finra.org/rules-guidance/rulebooks/finra-rules/3110)

[11] Financial Industry Regulatory Authority. *Rule 4511. General Requirements*. [FINRA](https://www.finra.org/rules-guidance/rulebooks/finra-rules/4511)

[12] Harold Booth, Murugiah Souppaya, Apostol Vassilev, Michael Ogata, Martin Stanley, and Karen Scarfone. *Secure Software Development Practices for Generative AI and Dual-Use Foundation Models: An SSDF Community Profile*. NIST SP 800-218A, 2024. [DOI](https://doi.org/10.6028/NIST.SP.800-218A)
