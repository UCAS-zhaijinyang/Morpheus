# 4 Morpheus-Datasets

Morpheus-Datasets is designed for insider-threat detection in enterprise workflows that include delegated AI execution. The modeling starts with ordinary work and asks when an action that appears routine becomes unauthorized because its purpose, authority, information flow, or persistent procedure has changed. This section explains the prior work that we inherit, the new modeling ideas introduced by Morpheus, the rationale for the three organizational settings, and the generation configuration used for the dataset.

## 4.1 Threat-Modeling Rationale

### 4.1.1 Inheritance from Prior Work

Morpheus inherits the authorized-access view of insider threat. CISA defines insider threat around a current or former member's authorized access or organizational knowledge and the possibility that this access or knowledge contributes to harm [1]. The CERT Insider Threat Test Dataset provides a complementary behavioral baseline with employee activity and scripted malicious behavior [3]. These sources establish two principles for our setting. An insider action may use a valid account, and the security meaning of an event cannot be inferred from the event type alone.

Our closest methodological predecessor is Chimera [2]. Chimera constructs organization profiles, role- and personality-conditioned employee agents, shared goals, schedules, ordinary interactions, threat behaviors, and unified logs. It embeds malicious behavior in routine work instead of presenting an isolated attack script. We inherit this ordinary-work embedding, the use of 5W1H to describe who, what, when, where, why, and how, and the mapping of attack stages to observable procedure evidence and detection data sources. Chimera also motivates using multiple organizational settings and long-horizon activity because an insider detector should be evaluated under normal collaboration and distribution shift.

We also inherit the policy perspective from attribute-based access control and purpose-restriction research. NIST SP 800-162 treats authorization as a function of the subject, object, operation, environment, and policy attributes [5]. Purpose-restriction research formalizes the fact that permission to read an object does not imply permission to use every derived result for every purpose [6]. NIST Zero Trust similarly requires access decisions to be evaluated in the current context [16]. Facade shows why user and resource context matters for high-precision insider-threat detection in enterprise logs [7]. These works guide the authorization questions in our scenarios, while Morpheus adds the organization and execution state needed for AI-mediated workflows.

MITRE ATT&CK supplies a shared vocabulary for valid accounts, repository collection, and service-based exfiltration [4]. We use that vocabulary to align stage evidence with established insider-threat procedures, while retaining the organizational purpose and Agent provenance that ATT&CK techniques do not express.

Recent AI-security work supplies the second part of the inherited foundation. NIST AI 600-1 identifies data privacy, information security, and human-AI configuration as generative-AI risk dimensions [8]. AgentDojo makes the path from external content to model reasoning, tool invocation, and environment state measurable [9]. OWASP's agentic risk taxonomy separates identity and privilege abuse, tool misuse, memory or context poisoning, and insecure inter-agent communication [10]. The study of malicious Agent skills provides evidence that reusable procedures can become a supply-chain attack surface [11]. These works motivate AI-specific observations, but they do not provide a single enterprise model that combines department purpose, delegated authority, Agent execution, and downstream effects.

The inherited unit is therefore a long-running, multi-agent representation of ordinary organizational activity with stage-level evidence. Morpheus extends the unit of analysis from an employee event or account-day to an organizationally constrained execution chain. The extension is introduced below as additions to the threat model, rather than as a replacement for Chimera's simulation philosophy.

### 4.1.2 Organization-Constrained Trajectory Generation

The first new idea is to treat organizational context as a security state variable. We arrived at this design by comparing insider-threat taxonomies, access-control research, enterprise workflow guidance, and the work patterns represented in our three scenario families. Across these sources, the same authorization questions recur. Which department owns the resource? Why is the requester involved in the project? Which dependency or reporting path makes the handoff plausible? What approval permits the action? For how long is the approval valid? Who may receive the resulting artifact? These questions are part of the security semantics of an event, not background text attached to a schedule.

We abstract the recurring patterns into an organization-constrained trajectory. The organization contains departments, employees, projects, resources, tools, and Agents linked by ownership, reporting, dependency, visibility, approval, and delegation relationships. A work item is admissible only when its role, resource, operation, business purpose, timing, and approval path are consistent with those relationships. This abstraction follows ABAC and purpose restrictions, while making the relationships between departments and projects explicit. It also preserves Chimera's principle that employees should be observed while pursuing plausible organizational goals.

This organization-first ordering is important for internal-threat modeling. A local permission check can succeed while the composed information flow violates the project purpose. For example, an employee may be temporarily assigned to support another department, receive a narrowly scoped document, and obtain a valid approval for a summary. Combining several such summaries for a recipient outside the dependency path can still exceed the original authorization. The threat in T2 is therefore defined by the global workflow and its final use, rather than by any single cross-department read. This captures low-and-slow behavior that account-centered logs tend to fragment.

The modeling philosophy is to study real workflows before writing attack cases. We first identify recurring organizational patterns such as incident response, regulated review, temporary coverage, model evaluation, and release approval. We then abstract their stable constraints and project those constraints into executable trajectories. The resulting trajectory retains normal task pressure, handoffs, approvals, and tool use. A threat intervention changes one organizational condition, such as a dependency edge, approval scope, delegation window, or recipient purpose. This makes the organizational constraint graph an experimental object. It is possible to ask whether changing a department goal affects that department and its dependents, whether removing a permission causes a legitimate alternative workflow, and whether an expired delegation prevents a downstream action.

### 4.1.3 AI-Mediated Execution and Provenance

The second new idea is to model AI execution as a distinct, traceable part of the authorization chain. In conventional insider-threat data, the employee account is often treated as both requester and executor. In Morpheus, the human employee may initiate or approve a task, a planner may decompose it, an enterprise Agent may retrieve or transform data, and a tool-facing Agent may issue the final API call. These roles can share an organizational identity while having different runtime state and delegated scope. Separating them allows a detector to distinguish who requested an action, who was authorized to perform it, which Agent executed it, and which resource or recipient was affected.

This separation also changes how we model AI data flows. We trace the source that enters an Agent context, the human purpose that authorized the task, the model or Agent context that processes the source, the tool call that creates an effect, and the recipient or state change that follows. T1 uses this chain to represent a legitimate source read followed by an output sent to an unapproved model endpoint, storage location, or recipient. The local read and the local tool call can look ordinary. The violation appears in the relationship between the source authorization, the delegated purpose, and the final data boundary. External content can be recorded as a source without being mislabeled as an insider. The insider label requires that the harmful effect depend on internal authority, organizational information, or an enterprise execution chain.

Morpheus also treats planning and handoff as security-relevant transitions. The execution path for a simple low-risk task can differ from the path for a multi-step or high-sensitivity task that requires planning, review, or delegation. The route, handoff, executor, tool invocation, policy decision, and resulting state are retained as one causal trace. This follows the trajectory-level emphasis of AgentDojo and policy-aware Agent auditing while placing the events inside a department and project context.

The framework's risk-complexity routing makes this distinction explicit. Low-risk state changes can remain on a direct path, while uncertain or sensitive tasks can require planning, review, or a human-Agent handoff. The route decision is retained as evidence because it explains how a request reached an executor and whether the chosen path was consistent with the task's organizational constraints.

The third addition within the AI model is a provenance-constrained skill automaton. A Skill or Memory item is an executable procedure, not merely text retrieved by similarity. Its safe reuse depends on where it came from, which role and department created it, which resources and recipients it covered, which preconditions and postconditions it had, whether it has expired, and whether the current task still satisfies those conditions. T3 models a procedure that was valid in an earlier context but is reused after the current role, purpose, tenancy, resource scope, or approval window changes. The threat is the resulting unauthorized tool effect and any subsequent propagation of the contaminated procedure. This design turns skill origin, scope, expiry, validation, and reuse into security variables while retaining the utility of normal workflow reuse.

The AI-specific philosophy is consequently provenance before intent. A natural-language instruction can describe a harmful goal, but it cannot by itself establish that the instruction was executed, that the execution violated a policy, or that an internal authority enabled the effect. Morpheus evaluates the full source-to-context-to-handoff-to-tool path and keeps the source, principal, executor, and effect distinct. This is the additional information needed to study delegation, data-boundary crossing, tool misuse, and persistent skill contamination in the same organizational setting.

## 4.2 Selection of Organizational Settings

We select the three settings because they exercise complementary authorization boundaries while retaining the ordinary employee collaboration that makes insider threats difficult to detect. The Internet setting emphasizes fast-moving service work and customer or tenant boundaries. The financial setting emphasizes formal supervision, approval validity, and records. The AI-company setting emphasizes data, model, and procedure provenance across an AI development lifecycle. Together they cover the three new Morpheus dimensions, data-flow purpose, organizational composition, and AI-mediated persistence, under distinct operational constraints.

**Internet software company.** We model a provider of online business software whose customer-support, engineering, and reliability teams handle incidents together. Google SRE guidance describes joint incident analysis, review of postmortems, and controlled handling of information that can identify users [13]. This creates frequent legitimate movement of data across teams and tools while retaining a clear customer or tenant boundary. The setting is well suited to T1 because a source read, model transformation, and incident update may all be routine, whereas the final recipient or external endpoint can violate the approved boundary. It also supplies normal cross-team handoffs for testing whether a detector distinguishes collaboration from disclosure.

**Financial institution.** We model a securities firm with research, risk, operations, and compliance functions. FINRA Rule 3110 requires supervisory systems and written procedures, while Rule 4511 addresses books and records [14, 15]. These requirements make approval, reviewer identity, retention, and validity windows natural parts of ordinary work. A risk review may legitimately aggregate information from several departments, yet the complete artifact may be unauthorized when the project, recipient, or approval scope changes. This setting therefore stresses T2 and provides a regulated workflow in which local authorization and global purpose can diverge.

**AI model development company.** We model an organization that spans data preparation, model evaluation, safety review, and release. NIST SP 800-218A emphasizes secure development practices for generative-AI and dual-use foundation-model systems [12]. In this setting, an evaluation artifact or reusable procedure is meaningful only with its experiment, version, owner, and intended use. Repeated evaluations and releases create legitimate opportunities for procedural reuse, while changes in data scope, tenant, role, or approval make stale reuse dangerous. This setting therefore stresses T3 and tests whether provenance-aware reuse can distinguish ordinary automation from skill or memory contamination.

The three settings are deliberately complementary rather than three instances of one industry. Their differences expose whether a detector relies on surface vocabulary or learns the authorization and provenance relations that define the threat. Their common structure preserves the possibility of matched cross-setting evaluation.

## 4.3 Data Generation Configuration

We configure generation with DeepSeek Harness, denoted deepseek-harness. The dataset contains one simulated organization for each of the three settings. Each organization has 100 simulated employees and a 50-workday horizon arranged as ten Monday-to-Friday weeks. The resulting baseline capacity is 5,000 employee-days per organization and 15,000 employee-days across the three settings. An employee-day represents the recorded activity of one employee during one simulated workday. Matched benign and threat trajectories are generated from the same organizational state and are counted as paired traces for evaluation.

The organization profile, employee roles, department relationships, project goals, schedule context, tools, Agent registry, and procedural-memory state are initialized independently for each setting. Daily work provides the ordinary activity in which the intervention is embedded. The generator records human and Agent participation, delegated execution, source and procedure provenance, tool effects, and the evidence used for the final label. These configuration choices define the target dataset scale and generation protocol. They do not by themselves constitute completed experimental results.

## References
[1] Cybersecurity and Infrastructure Security Agency. *Insider Threat Mitigation*. [CISA](https://www.cisa.gov/topics/physical-security/insider-threat-mitigation)

[2] Jiongchi Yu, Xiaofei Xie, Qiang Hu, Yuhan Ma, and Ziming Zhao. “Chimera: Harnessing Multi-Agent LLMs for Automatic Insider Threat Simulation.” *Network and Distributed System Security Symposium*, 2026. DOI: [10.14722/ndss.2026.240375](https://doi.org/10.14722/ndss.2026.240375)

[3] CERT Division, Software Engineering Institute, Carnegie Mellon University. *CERT Insider Threat Test Dataset*. 2020. [SEI](https://www.sei.cmu.edu/library/insider-threat-test-dataset/)

[4] MITRE. *Valid Accounts (T1078), Data from Information Repositories (T1213), and Exfiltration Over Web Service (T1567)*. [MITRE ATT&CK](https://attack.mitre.org/)

[5] Vincent C. Hu et al. *Guide to Attribute Based Access Control (ABAC) Definition and Considerations*. NIST SP 800-162, updated 2019. [NIST](https://csrc.nist.gov/pubs/sp/800/162/upd2/final)

[6] Michael Carl Tschantz, Anupam Datta, and Jeannette M. Wing. “Formalizing and Enforcing Purpose Restrictions in Privacy Policies.” *IEEE Symposium on Security and Privacy*, 2012. [DOI](https://doi.org/10.1109/SP.2012.21)

[7] Alex Kantchelian et al. “Facade: High-Precision Insider Threat Detection Using Deep Contextual Anomaly Detection.” *35th USENIX Security Symposium*, 2026. [USENIX](https://www.usenix.org/conference/usenixsecurity26/presentation/kantchelian)

[8] Chloe Autio et al. *Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile*. NIST AI 600-1, 2024. [DOI](https://doi.org/10.6028/NIST.AI.600-1)

[9] Edoardo Debenedetti et al. “AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents.” *Advances in Neural Information Processing Systems*, 37, 2024. [NeurIPS](https://proceedings.neurips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html)

[10] OWASP GenAI Security Project. *OWASP Top 10 for Agentic Applications, 2026*. [OWASP](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)

[11] Yi Liu et al. “Do Not Mention This to the User: Detecting and Understanding Malicious Agent Skills in the Wild.” *35th USENIX Security Symposium*, 2026. [USENIX](https://www.usenix.org/conference/usenixsecurity26/presentation/liu-yi)

[12] Harold Booth et al. *Secure Software Development Practices for Generative AI and Dual-Use Foundation Models: An SSDF Community Profile*. NIST SP 800-218A, 2024. [DOI](https://doi.org/10.6028/NIST.SP.800-218A)

[13] John Lunney and Sue Lueder. “Postmortem Culture: Learning from Failure.” In *Site Reliability Engineering*, 2016. [Google SRE](https://sre.google/sre-book/postmortem-culture/)

[14] Financial Industry Regulatory Authority. *Rule 3110. Supervision*. [FINRA](https://www.finra.org/rules-guidance/rulebooks/finra-rules/3110)

[15] Financial Industry Regulatory Authority. *Rule 4511. General Requirements*. [FINRA](https://www.finra.org/rules-guidance/rulebooks/finra-rules/4511)

[16] Scott Rose et al. *Zero Trust Architecture*. NIST SP 800-207, 2020. [NIST](https://csrc.nist.gov/pubs/sp/800/207/final)

---

# 4 Morpheus-Datasets 数据集

Morpheus-Datasets 面向包含 AI 委托执行的企业工作流，生成用于内部威胁检测的行为轨迹。威胁建模从日常工作出发，考察一个看似普通的操作何时因为业务目的、授权关系、信息流或持久化流程发生变化而越界。本节说明我们继承的前人工作、Morpheus 新增的建模思想、三个组织场景的选择依据，以及数据集的生成配置。

## 4.1 威胁建模依据

### 4.1.1 对前人工作的继承

Morpheus 继承基于授权访问的内部威胁定义。CISA 将内部威胁建立在当前或曾经的组织成员拥有授权访问权限或组织知识，并可能利用这种访问或知识造成损害的基础上 [1]。CERT Insider Threat Test Dataset 则提供了员工活动和脚本化恶意行为组成的行为基线 [3]。这两类工作共同确立了两个原则。内部威胁可以使用有效账号，事件类型本身不足以决定一次操作的安全含义。

与我们最接近的方法前身是 Chimera [2]。Chimera 构建组织画像、带有角色和个性的员工 Agent、共同目标、日程、日常交互、威胁行为及统一日志。它把恶意行为嵌入常规工作，而不是写成孤立的攻击脚本。我们继承这种日常工作嵌入方式，继承使用 5W1H 描述谁、做什么、何时、何地、为什么和如何做，并继承把攻击阶段映射到可观察的步骤证据和检测数据源。Chimera 还说明，应通过多个组织场景和长时间行为评测内部威胁检测，因为检测器需要面对正常协作和分布变化。

我们同时继承基于策略的授权视角。NIST SP 800-162 将授权描述为主体、对象、操作、环境和策略属性共同作用的结果 [5]。用途限制研究形式化了一个重要事实，允许读取某个对象，并不意味着允许将其派生结果用于任何目的 [6]。NIST Zero Trust 同样要求在当前情境下重新评估访问请求 [16]。Facade 说明了在企业日志中联合使用用户和资源上下文对高精度内部威胁检测的重要性 [7]。这些工作为场景中的授权判断提供依据，Morpheus 则进一步加入了 AI 委托工作流所需的组织状态和执行状态。

MITRE ATT&CK 为有效账号、信息库收集和基于服务的外传提供了共同的攻击步骤词汇 [4]。我们用这一词汇对齐已有内部威胁程序证据，同时保留 ATT&CK 技术本身没有表达的组织目的和 Agent 来源信息。

近期 AI 安全研究构成第二部分基础。NIST AI 600-1 将数据隐私、信息安全和人机配置列为生成式 AI 的风险维度 [8]。AgentDojo 使外部内容、模型推理、工具调用和环境状态之间的路径可以被观测 [9]。OWASP 的 Agent 风险分类分别讨论身份和权限滥用、工具误用、记忆或上下文污染以及不安全的 Agent 间通信 [10]。针对恶意 Agent Skill 的研究表明，可复用流程可以成为供应链攻击面 [11]。这些工作为 AI 特有的观测内容提供依据，但没有提供一个同时表达部门目的、委托权限、Agent 执行和下游效果的企业威胁模型。

因此，我们继承的是带有阶段证据的长期、多 Agent 日常组织活动表示。Morpheus 把分析单位从员工事件或账号日扩展为受组织约束的执行链。下面的内容是对威胁模型的新增，而不是替换 Chimera 的仿真思想。

### 4.1.2 组织约束下的轨迹生成

第一项新增思想是把组织情境作为安全状态变量。我们对内部威胁分类、访问控制研究、企业流程规范和三个场景中的工作模式进行对照，得到了一组反复出现的授权问题。资源由哪个部门负责？请求者为什么参与该项目？哪条依赖关系或汇报路径使交接合理？哪个审批允许该操作？审批有效多久？结果可以发送给谁？这些问题构成事件的安全语义，不能被当作附加在日程后的背景文字。

我们将这些重复出现的模式抽象为组织约束下的行为轨迹。组织由部门、员工、项目、资源、工具和 Agent 构成，并通过所有权、汇报、依赖、可见性、审批和委托关系连接。只有当岗位、资源、操作、业务目的、时间和审批路径与这些关系一致时，工作项才是可接受的。这一抽象遵循 ABAC 和用途限制思想，同时显式表达部门与项目之间的关系，也保留 Chimera 让员工围绕合理组织目标工作的原则。

把组织约束放在前面对于内部威胁建模很重要。局部权限检查可以成功，但组合后的信息流仍可能违反项目目的。例如，员工可以被临时安排去支持另一个部门，可以获得范围有限的文档，也可以获得发送摘要的有效审批。若把多个摘要组合后发送给依赖路径之外的接收者，完整操作仍可能超出原始授权。T2 的威胁因此由整体工作流及其最终用途定义，而不是由某一次跨部门读取定义。这种设计表达了账号级日志容易切碎的低频渐进式行为。

我们的建模思想是先研究真实工作流，再编写攻击案例。我们先从事件响应、受监管复核、临时替岗、模型评测和发布审批等流程中提取重复模式，再抽象其稳定约束，并把约束投影到可执行轨迹中。轨迹保留日常任务压力、交接、审批和工具使用。威胁干预只改变一个组织条件，例如依赖边、审批范围、委托有效期或接收者用途。这样，组织约束图就成为可实验的研究对象。我们可以检验改变部门目标是否主要影响该部门及其依赖方，撤销权限是否触发合法替代流程，以及过期委托是否阻止下游操作。

### 4.1.3 AI 介导的执行与来源溯源

第二项新增思想是把 AI 执行建模为授权链中独立且可追溯的部分。在传统内部威胁数据中，员工账号通常同时被视为请求者和执行者。在 Morpheus 中，员工可以发起或批准任务，规划 Agent 可以分解任务，企业 Agent 可以检索或转换数据，工具 Agent 可以发出最终 API 调用。这些角色可能属于同一组织身份，但其运行时状态和委托范围不同。将它们分开，可以区分谁请求了操作、谁获准执行操作、哪个 Agent 实际执行，以及哪个资源或接收者受到影响。

这种区分也改变了 AI 数据流的建模方式。我们追踪进入 Agent 上下文的来源、获批任务的人类目的、处理来源的模型或 Agent 上下文、产生效果的工具调用，以及后续的接收者或状态变化。T1 用这条链表示一种场景，员工合法读取源数据，但生成结果被发送到未经批准的模型端点、存储位置或接收者。局部读取和局部工具调用都可能看似正常，违规出现在源数据授权、委托目的和最终数据边界之间的关系上。外部内容可以被记录为来源，但不会因此被标记为内部人员。只有当危害依赖内部授权、组织信息或企业执行链时，样本才获得内部威胁标签。

Morpheus 还把规划和交接作为安全相关的状态转移。简单低风险任务可以采用直接执行路径，多步骤或高敏感度任务则可能需要规划、复核或委托。路由、交接、执行者、工具调用、策略判定和结果状态被保留在同一条因果轨迹中。这继承了 AgentDojo 和策略感知 Agent 审计对轨迹的重视，并把这些事件放入部门和项目情境中。

框架中的风险—复杂度路由使这种区别变得显式。低风险状态变化可以沿直接路径执行，不确定或敏感任务则可以要求规划、复核或人类—Agent 交接。路由决策也被保留为证据，因为它解释了请求如何到达执行者，以及所选路径是否符合任务的组织约束。

AI 模型中的第三项新增内容是受来源约束的技能自动机。Skill 或 Memory 是可执行流程，不只是按相似度检索出的文本。安全复用取决于它的来源、创建它的岗位和部门、覆盖的资源和接收者、前置和后置条件、有效期，以及当前任务是否仍满足这些条件。T3 模拟一种流程，它在早期任务中有效，但当前员工、用途、租户、资源范围或审批窗口变化后仍被复用。威胁表现为由此产生的未授权工具效果，以及被污染流程随后传播的影响。该设计把技能来源、范围、有效期、验证和复用变成安全变量，同时保留正常工作流复用带来的效率。

因此，AI 相关建模遵循来源优先于意图的原则。自然语言指令可以描述一个有害目标，但不能单独证明指令已经执行，不能证明执行违反了策略，也不能证明内部授权导致了实际效果。Morpheus 评估完整的来源、上下文、交接和工具路径，并区分来源、主体、执行者和效果。这样才能在同一组织情境中研究委托、数据边界跨越、工具误用和持久化技能污染。

## 4.2 组织场景选择

选择这三个场景，是因为它们在保留日常员工协作的同时，分别施加互补的授权边界。互联网场景强调快速变化的服务工作以及客户或租户边界。金融场景强调正式监督、审批有效性和记录保存。AI 公司场景强调 AI 开发生命周期中的数据、模型和流程来源。三个场景共同覆盖 Morpheus 的三类新增维度，即数据流用途、组织组合以及 AI 介导的持久化，同时保持不同的业务约束。

**互联网软件公司。** 我们模拟一家面向企业客户的在线软件服务商，由客户支持、工程和可靠性团队共同处理事件。Google SRE 指南描述了共同分析事件、审阅复盘报告，以及受控处理可识别用户信息的实践 [13]。因此，数据在团队和工具之间移动是正常工作的一部分，同时仍然受客户或租户边界约束。该场景适合 T1，因为读取源数据、进行模型转换和更新事件记录都可能是正常行为，而最终接收者或外部端点可能越过获批边界。它也提供了大量正常跨团队交接，用于检验检测器是否能把协作与披露区分开。

**金融机构。** 我们模拟一家具有研究、风险、运营和合规职能的证券机构。FINRA Rule 3110 要求监督体系和书面程序，Rule 4511 涉及账簿和记录保存 [14, 15]。这些要求使审批、复核人、留存和有效期自然成为日常工作的一部分。风险审查可以合法汇总多个部门的信息，但当项目、接收者或审批范围发生变化时，完整产物可能不再获批。因此，该场景重点检验 T2，并提供一个能够区分局部授权和整体业务目的的受监管流程。

**AI 模型研发公司。** 我们模拟一家覆盖数据准备、模型评测、安全审查和发布流程的组织。NIST SP 800-218A 强调生成式 AI 和双用途基础模型系统的安全开发实践 [12]。在该场景中，评测产物或可复用流程必须与实验、版本、所有者和预期用途关联。重复评测和发布为流程复用提供正常机会，而数据范围、租户、岗位或审批变化会使过期复用产生风险。因此，该场景重点检验 T3，并考察带有来源约束的复用能否区分正常自动化与技能或记忆污染。

三个场景不是同一行业的重复实例，而是互补的组织环境。它们可以检验检测器是否依赖表面词汇，或者是否学习定义威胁的授权和来源关系。共同的工作流结构也保留了跨场景配对评测的可能性。

## 4.3 数据生成配置

我们使用 DeepSeek Harness（deepseek-harness）进行数据生成。数据集为三个场景分别设置一个模拟组织。每个组织包含 100 名模拟员工，覆盖 50 个模拟工作日，按周一至周五安排为 10 个工作周。每个组织的基线规模为 5,000 个员工日，三个组织合计 15,000 个员工日。一个员工日表示一名员工在一个模拟工作日中的活动记录。正常轨迹和威胁轨迹从同一组织状态生成，并作为配对轨迹用于评测。

每个场景独立初始化组织画像、员工角色、部门关系、项目目标、日程情境、工具、Agent 注册信息和程序性记忆状态。日常工作提供干预所嵌入的行为背景。生成过程记录人类和 Agent 的参与、委托执行、来源与流程溯源、工具效果及最终标注所需的证据。这些配置明确了目标数据集规模和生成协议，并不等同于已经完成的实验结果。

## 参考文献

[1] Cybersecurity and Infrastructure Security Agency. *Insider Threat Mitigation*. [CISA](https://www.cisa.gov/topics/physical-security/insider-threat-mitigation)

[2] Jiongchi Yu, Xiaofei Xie, Qiang Hu, Yuhan Ma, and Ziming Zhao. “Chimera: Harnessing Multi-Agent LLMs for Automatic Insider Threat Simulation.” *Network and Distributed System Security Symposium*, 2026. DOI: [10.14722/ndss.2026.240375](https://doi.org/10.14722/ndss.2026.240375)

[3] CERT Division, Software Engineering Institute, Carnegie Mellon University. *CERT Insider Threat Test Dataset*. 2020. [SEI](https://www.sei.cmu.edu/library/insider-threat-test-dataset/)

[4] MITRE. *Valid Accounts (T1078), Data from Information Repositories (T1213), and Exfiltration Over Web Service (T1567)*. [MITRE ATT&CK](https://attack.mitre.org/)

[5] Vincent C. Hu et al. *Guide to Attribute Based Access Control (ABAC) Definition and Considerations*. NIST SP 800-162, updated 2019. [NIST](https://csrc.nist.gov/pubs/sp/800/162/upd2/final)

[6] Michael Carl Tschantz, Anupam Datta, and Jeannette M. Wing. “Formalizing and Enforcing Purpose Restrictions in Privacy Policies.” *IEEE Symposium on Security and Privacy*, 2012. [DOI](https://doi.org/10.1109/SP.2012.21)

[7] Alex Kantchelian et al. “Facade: High-Precision Insider Threat Detection Using Deep Contextual Anomaly Detection.” *35th USENIX Security Symposium*, 2026. [USENIX](https://www.usenix.org/conference/usenixsecurity26/presentation/kantchelian)

[8] Chloe Autio et al. *Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile*. NIST AI 600-1, 2024. [DOI](https://doi.org/10.6028/NIST.AI.600-1)

[9] Edoardo Debenedetti et al. “AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents.” *Advances in Neural Information Processing Systems*, 37, 2024. [NeurIPS](https://proceedings.neurips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html)

[10] OWASP GenAI Security Project. *OWASP Top 10 for Agentic Applications, 2026*. [OWASP](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)

[11] Yi Liu et al. “Do Not Mention This to the User: Detecting and Understanding Malicious Agent Skills in the Wild.” *35th USENIX Security Symposium*, 2026. [USENIX](https://www.usenix.org/conference/usenixsecurity26/presentation/liu-yi)

[12] Harold Booth et al. *Secure Software Development Practices for Generative AI and Dual-Use Foundation Models: An SSDF Community Profile*. NIST SP 800-218A, 2024. [DOI](https://doi.org/10.6028/NIST.SP.800-218A)

[13] John Lunney and Sue Lueder. “Postmortem Culture: Learning from Failure.” In *Site Reliability Engineering*, 2016. [Google SRE](https://sre.google/sre-book/postmortem-culture/)

[14] Financial Industry Regulatory Authority. *Rule 3110. Supervision*. [FINRA](https://www.finra.org/rules-guidance/rulebooks/finra-rules/3110)

[15] Financial Industry Regulatory Authority. *Rule 4511. General Requirements*. [FINRA](https://www.finra.org/rules-guidance/rulebooks/finra-rules/4511)

[16] Scott Rose et al. *Zero Trust Architecture*. NIST SP 800-207, 2020. [NIST](https://csrc.nist.gov/pubs/sp/800/207/final)
