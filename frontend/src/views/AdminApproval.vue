<template>
  <div class="admin-approval">
    <el-header class="admin-header">
      <div class="header-left">
        <el-icon size="28" color="#f59e0b"><Setting /></el-icon>
        <span class="system-name">智慧骨科云平台</span>
        <el-tag size="small" type="warning">管理后台</el-tag>
      </div>
      <div class="header-right">
        <span class="welcome-text">管理员：{{ adminInfo.username }}</span>
        <el-button type="danger" size="small" @click="handleLogout">退出</el-button>
      </div>
    </el-header>

    <el-container class="admin-container">
      <el-aside width="200px" class="admin-sidebar">
        <el-menu :default-active="activeMenu" class="admin-menu" @select="handleMenuSelect">
          <el-menu-item index="approvals">
            <el-icon><DocumentChecked /></el-icon>
            <span>医生审核</span>
            <el-badge v-if="pendingCount > 0" :value="pendingCount" class="menu-badge" />
          </el-menu-item>
          <el-menu-item index="doctors">
            <el-icon><FirstAidKit /></el-icon>
            <span>医生管理</span>
          </el-menu-item>
          <el-menu-item index="patients">
            <el-icon><User /></el-icon>
            <span>患者管理</span>
          </el-menu-item>
          <el-menu-item index="detection">
            <el-icon><Camera /></el-icon>
            <span>检测系统</span>
          </el-menu-item>
          <el-menu-item index="training">
            <el-icon><MagicStick /></el-icon>
            <span>模型训练</span>
          </el-menu-item>
          <el-menu-item index="analysis">
            <el-icon><TrendCharts /></el-icon>
            <span>数据分析</span>
          </el-menu-item>
          <el-menu-item index="statistics">
            <el-icon><DataAnalysis /></el-icon>
            <span>统计分析</span>
          </el-menu-item>
          <el-menu-item index="logs">
            <el-icon><Document /></el-icon>
            <span>操作日志</span>
          </el-menu-item>
          <el-menu-item index="announcements">
            <el-icon><Bell /></el-icon>
            <span>公告管理</span>
          </el-menu-item>
          <el-menu-item index="datasets">
            <el-icon><Folder /></el-icon>
            <span>数据集管理</span>
          </el-menu-item>
          <el-menu-item index="data-generator">
            <el-icon><MagicStick /></el-icon>
            <span>数据生成工具</span>
          </el-menu-item>
          <el-menu-item index="system">
            <el-icon><Setting /></el-icon>
            <span>系统设置</span>
          </el-menu-item>
        </el-menu>
      </el-aside>

      <el-main class="admin-main">
        <!-- 医生审核 -->
        <div v-if="activeMenu === 'approvals'" class="page-content">
          <h2 class="page-title">医生注册审核</h2>
          <el-card shadow="never">
            <el-tabs v-model="approvalTab">
              <el-tab-pane label="待审核" name="pending">
                <el-table :data="pendingApprovals" style="width: 100%">
                  <el-table-column prop="full_name" label="姓名" width="100" />
                  <el-table-column prop="hospital" label="所属医院" width="150" />
                  <el-table-column prop="department" label="科室" width="120" />
                  <el-table-column prop="title" label="职称" width="100" />
                  <el-table-column prop="license_number" label="执业证号" width="150" />
                  <el-table-column prop="phone" label="联系电话" width="130" />
                  <el-table-column label="申请时间" width="150">
                    <template #default="{ row }">
                      {{ formatDateTime(row.created_at) }}
                    </template>
                  </el-table-column>
                  <el-table-column label="操作" width="200" fixed="right">
                    <template #default="{ row }">
                      <el-button link type="primary" @click="viewDetail(row)">查看详情</el-button>
                      <el-button link type="success" @click="approveDoctor(row)">通过</el-button>
                      <el-button link type="danger" @click="rejectDoctor(row)">拒绝</el-button>
                    </template>
                  </el-table-column>
                </el-table>
              </el-tab-pane>
              <el-tab-pane label="已审核" name="processed">
                <el-table :data="processedApprovals" style="width: 100%">
                  <el-table-column prop="full_name" label="姓名" width="100" />
                  <el-table-column prop="hospital" label="所属医院" width="150" />
                  <el-table-column prop="department" label="科室" width="120" />
                  <el-table-column prop="status" label="状态" width="100">
                    <template #default="{ row }">
                      <el-tag :type="row.status === 'approved' ? 'success' : 'danger'">
                        {{ row.status === 'approved' ? '已通过' : '已拒绝' }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="review_note" label="审核备注" show-overflow-tooltip />
                  <el-table-column label="审核时间" width="150">
                    <template #default="{ row }">
                      {{ formatDateTime(row.reviewed_at) }}
                    </template>
                  </el-table-column>
                </el-table>
              </el-tab-pane>
            </el-tabs>
          </el-card>
        </div>

        <!-- 医生管理 -->
        <div v-if="activeMenu === 'doctors'" class="page-content">
          <h2 class="page-title">医生管理</h2>
          <el-card shadow="never">
            <el-table :data="doctors" style="width: 100%">
              <el-table-column prop="full_name" label="姓名" width="100" />
              <el-table-column prop="hospital" label="所属医院" width="150" />
              <el-table-column prop="department" label="科室" width="120" />
              <el-table-column prop="title" label="职称" width="100" />
              <el-table-column prop="phone" label="联系电话" width="130" />
              <el-table-column prop="status" label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'active' ? 'success' : 'info'">
                    {{ row.status === 'active' ? '正常' : '停用' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="200" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" @click="viewDoctor(row)">查看</el-button>
                  <el-button link type="primary" @click="editDoctor(row)">编辑</el-button>
                  <el-button link type="danger" @click="disableDoctor(row)">停用</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </div>

        <!-- 患者管理 -->
        <div v-if="activeMenu === 'patients'" class="page-content">
          <h2 class="page-title">患者管理</h2>
          <el-card shadow="never">
            <el-table :data="patients.filter(p => p.full_name)" style="width: 100%">
              <el-table-column prop="full_name" label="姓名" width="100" />
              <el-table-column prop="patient_number" label="病历号" width="120" />
              <el-table-column prop="gender" label="性别" width="80" />
              <el-table-column prop="phone" label="联系电话" width="130" />
              <el-table-column label="注册时间" width="150">
                <template #default="{ row }">
                  {{ formatDate(row.created_at) }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="150" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" @click="viewPatient(row)">查看</el-button>
                  <el-button link type="primary" @click="editPatient(row)">编辑</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </div>

        <!-- 操作日志 -->
        <div v-if="activeMenu === 'logs'" class="page-content">
          <h2 class="page-title">操作日志</h2>
          
          <!-- 搜索栏 -->
          <el-row :gutter="16" style="margin-bottom: 16px">
            <el-col :span="5">
              <el-input
                v-model="logSearchForm.username"
                placeholder="搜索用户名"
                clearable
                @keyup.enter="handleLogSearch"
              >
                <template #prefix>
                  <el-icon><Search /></el-icon>
                </template>
              </el-input>
            </el-col>
            <el-col :span="4">
              <el-select
                v-model="logSearchForm.method"
                placeholder="请求方法"
                clearable
                style="width: 100%"
              >
                <el-option label="GET" value="GET" />
                <el-option label="POST" value="POST" />
                <el-option label="PUT" value="PUT" />
                <el-option label="DELETE" value="DELETE" />
              </el-select>
            </el-col>
            <el-col :span="4">
              <el-select
                v-model="logSearchForm.success"
                placeholder="执行状态"
                clearable
                style="width: 100%"
              >
                <el-option label="成功" :value="true" />
                <el-option label="失败" :value="false" />
              </el-select>
            </el-col>
            <el-col :span="7">
              <el-date-picker
                v-model="logSearchForm.dateRange"
                type="datetimerange"
                range-separator="至"
                start-placeholder="开始时间"
                end-placeholder="结束时间"
                style="width: 100%"
                format="YYYY-MM-DD HH:mm:ss"
                value-format="YYYY-MM-DD HH:mm:ss"
              />
            </el-col>
            <el-col :span="4">
              <el-button type="primary" @click="handleLogSearch">
                <el-icon><Search /></el-icon>
                搜索
              </el-button>
              <el-button @click="resetLogSearch">重置</el-button>
            </el-col>
          </el-row>

          <!-- 日志表格 -->
          <el-table :data="logList" style="width: 100%" v-loading="logLoading" border>
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="username" label="用户名" width="120" />
            <el-table-column prop="method" label="方法" width="80">
              <template #default="{ row }">
                <el-tag :type="getMethodType(row.method)" size="small">
                  {{ row.method }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="url" label="请求路径" min-width="200" show-overflow-tooltip />
            <el-table-column prop="description" label="操作描述" min-width="150" show-overflow-tooltip />
            <el-table-column prop="ip" label="IP地址" width="130" />
            <el-table-column prop="success" label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.success ? 'success' : 'danger'" size="small">
                  {{ row.success ? '成功' : '失败' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="时间" width="180">
              <template #default="{ row }">
                {{ formatLogTime(row.timestamp) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120" fixed="right" align="center">
              <template #default="{ row }">
                <el-button type="primary" size="small" @click="showLogDetail(row)">
                  详情
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- 分页 -->
          <el-pagination
            :current-page="logPagination.page"
            :page-size="logPagination.per_page"
            :total="logPagination.total"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next, jumper"
            style="margin-top: 16px; justify-content: flex-end"
            @update:current-page="logPagination.page = $event"
            @update:page-size="logPagination.per_page = $event"
            @size-change="handleLogSizeChange"
            @current-change="handleLogPageChange"
          />

          <!-- 详情对话框 -->
          <el-dialog v-model="logDetailVisible" title="日志详情" width="700px">
            <el-descriptions :column="1" border v-if="currentLog">
              <el-descriptions-item label="日志ID">
                {{ currentLog.id }}
              </el-descriptions-item>
              <el-descriptions-item label="用户名">
                {{ currentLog.username }}
              </el-descriptions-item>
              <el-descriptions-item label="请求方法">
                <el-tag :type="getMethodType(currentLog.method)">
                  {{ currentLog.method }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="请求路径">
                {{ currentLog.url }}
              </el-descriptions-item>
              <el-descriptions-item label="IP地址">
                {{ currentLog.ip || '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="User-Agent">
                <div style="word-break: break-all">
                  {{ currentLog.user_agent || '-' }}
                </div>
              </el-descriptions-item>
              <el-descriptions-item label="操作描述">
                {{ currentLog.description || '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="执行状态">
                <el-tag :type="currentLog.success ? 'success' : 'danger'">
                  {{ currentLog.success ? '成功' : '失败' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="错误信息" v-if="!currentLog.success && currentLog.error_msg">
                <div style="color: #f56c6c; word-break: break-all">
                  {{ currentLog.error_msg }}
                </div>
              </el-descriptions-item>
              <el-descriptions-item label="操作时间">
                {{ formatLogTime(currentLog.timestamp) }}
              </el-descriptions-item>
            </el-descriptions>
          </el-dialog>
        </div>

        <!-- 数据生成工具 -->
        <div v-if="activeMenu === 'data-generator'" class="page-content">
          <h2 class="page-title">数据生成工具</h2>
          
          <el-row :gutter="20">
            <el-col :span="12">
              <el-card shadow="never">
                <template #header>
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span>生成测试数据</span>
                    <el-tag type="warning">管理员功能</el-tag>
                  </div>
                </template>
                
                <el-form label-width="120px">
                  <el-form-item label="患者数量">
                    <el-input-number v-model="testDataConfig.patientCount" :min="1" :max="100" />
                  </el-form-item>
                  <el-form-item label="检查记录数量">
                    <el-input-number v-model="testDataConfig.examCount" :min="1" :max="200" />
                  </el-form-item>
                  <el-form-item>
                    <el-button type="primary" @click="generateTestData" :loading="generatingData">
                      <el-icon><MagicStick /></el-icon>
                      一键生成测试数据
                    </el-button>
                  </el-form-item>
                </el-form>
                
                <el-alert
                  v-if="generateResult.message"
                  :title="generateResult.message"
                  :type="generateResult.success ? 'success' : 'error'"
                  show-icon
                  style="margin-top: 20px"
                />
              </el-card>
            </el-col>
            
            <el-col :span="12">
              <el-card shadow="never">
                <template #header>
                  <span>数据说明</span>
                </template>
                <div style="line-height: 1.8; color: #606266;">
                  <p><strong>功能说明：</strong></p>
                  <ul style="margin-left: 20px; margin-bottom: 16px;">
                    <li>自动生成随机的患者信息（姓名、年龄、性别等）</li>
                    <li>自动生成检查记录和检测结果</li>
                    <li>模拟真实的骨折类型分布（60%阳性率）</li>
                    <li>生成最近一年内的随机检查日期</li>
                  </ul>
                  <p><strong>数据范围：</strong></p>
                  <ul style="margin-left: 20px;">
                    <li>患者年龄：18-85岁</li>
                    <li>性别：男/女随机分布</li>
                    <li>骨折类型：撕脱、粉碎性、压缩性等</li>
                    <li>检查医生：张医生、李医生、王医生、刘医生</li>
                  </ul>
                </div>
              </el-card>
            </el-col>
          </el-row>
          
          <el-card shadow="never" style="margin-top: 20px;">
            <template #header>
              <span>当前数据统计</span>
            </template>
            <el-row :gutter="20">
              <el-col :span="8">
                <div style="text-align: center; padding: 20px;">
                  <div style="font-size: 36px; font-weight: bold; color: #1890ff;">{{ currentStats.patients }}</div>
                  <div style="color: #606266; margin-top: 8px;">患者总数</div>
                </div>
              </el-col>
              <el-col :span="8">
                <div style="text-align: center; padding: 20px;">
                  <div style="font-size: 36px; font-weight: bold; color: #52c41a;">{{ currentStats.examinations }}</div>
                  <div style="color: #606266; margin-top: 8px;">检查记录数</div>
                </div>
              </el-col>
              <el-col :span="8">
                <div style="text-align: center; padding: 20px;">
                  <div style="font-size: 36px; font-weight: bold; color: #722ed1;">{{ currentStats.users }}</div>
                  <div style="color: #606266; margin-top: 8px;">系统用户数</div>
                </div>
              </el-col>
            </el-row>
          </el-card>
        </div>

        <!-- 系统设置 -->
        <div v-if="activeMenu === 'system'" class="page-content">
          <h2 class="page-title">系统设置</h2>
          
          <!-- 基础设置 -->
          <el-card shadow="never" style="margin-bottom: 20px;">
            <template #header>
              <div style="font-weight: 600;">基础设置</div>
            </template>
            <el-form label-width="180px" style="max-width: 600px">
              <el-form-item label="系统名称">
                <el-input v-model="systemConfig.name" placeholder="请输入系统名称" />
              </el-form-item>
              <el-form-item label="验证码有效期">
                <el-input-number v-model="systemConfig.captchaTimeout" :min="1" :max="60" />
                <span class="form-unit">分钟</span>
              </el-form-item>
              <el-form-item label="医生审核开关">
                <el-switch v-model="systemConfig.doctorApproval" active-text="开启" inactive-text="关闭" />
              </el-form-item>
            </el-form>
          </el-card>

          <!-- 模型设置 -->
          <el-card shadow="never" style="margin-bottom: 20px;">
            <template #header>
              <div style="font-weight: 600;">模型设置</div>
            </template>
            <el-form label-width="180px" style="max-width: 600px">
              <el-form-item label="默认模型">
                <el-select v-model="aiSettings.default_model" placeholder="选择默认模型" style="width: 200px">
                  <el-option-group label="系统模型" v-if="systemModelsForSettings.length > 0">
                    <el-option
                      v-for="m in systemModelsForSettings"
                      :key="m.key"
                      :label="m.name"
                      :value="m.key"
                    />
                  </el-option-group>
                  <el-option-group label="自定义模型" v-if="customModelsForSettings.length > 0">
                    <el-option
                      v-for="m in customModelsForSettings"
                      :key="m.key"
                      :label="m.name"
                      :value="m.key"
                    />
                  </el-option-group>
                </el-select>
              </el-form-item>
              <el-form-item label="置信度阈值">
                <el-input-number v-model="aiSettings.confidence_threshold" :min="0" :max="1" :step="0.01" />
              </el-form-item>
            </el-form>
          </el-card>

          <!-- AI服务设置 -->
          <el-card shadow="never">
            <template #header>
              <div style="font-weight: 600;">AI服务设置</div>
            </template>
            <el-form label-width="180px" style="max-width: 600px">
              <el-form-item label="AI服务提供商">
                <el-radio-group v-model="aiSettings.ai_provider" @change="onProviderChange">
                  <el-radio label="local">本地部署 (Qwen3-VL)</el-radio>
                  <el-radio label="openai">OpenAI API</el-radio>
                  <el-radio label="modelscope">ModelScope API</el-radio>
                  <el-radio label="custom">自定义API</el-radio>
                </el-radio-group>
              </el-form-item>

              <!-- 本地部署配置 -->
              <div v-if="aiSettings.ai_provider === 'local'" class="ai-config-section">
                <el-alert
                  title="使用本地部署的Qwen3-VL-4B模型"
                  description="需要启动AI服务 (python AI/app.py)，无需API密钥"
                  type="info"
                  :closable="false"
                />
              </div>

              <!-- OpenAI配置 -->
              <div v-if="aiSettings.ai_provider === 'openai'" class="ai-config-section">
                <el-form-item label="API密钥">
                  <el-input
                    v-model="aiSettings.ai_api_key"
                    type="password"
                    placeholder="sk-xxxxxxxxxxxxxxxx"
                    show-password
                  />
                </el-form-item>
                <el-form-item label="模型">
                  <el-select v-model="aiSettings.ai_model" placeholder="选择模型" filterable allow-create>
                    <el-option label="GPT-4" value="gpt-4" />
                    <el-option label="GPT-4 Turbo" value="gpt-4-turbo-preview" />
                    <el-option label="GPT-3.5 Turbo" value="gpt-3.5-turbo" />
                    <el-option label="GPT-4o" value="gpt-4o" />
                  </el-select>
                </el-form-item>
              </div>

              <!-- ModelScope配置 -->
              <div v-if="aiSettings.ai_provider === 'modelscope'" class="ai-config-section">
                <el-alert
                  title="使用ModelScope API"
                  description="支持多模态大模型，需要ModelScope Token"
                  type="info"
                  :closable="false"
                  style="margin-bottom: 16px;"
                />
                <el-form-item label="模型ID">
                  <el-select 
                    v-model="aiSettings.ai_model" 
                    placeholder="选择或输入模型ID"
                    filterable
                    allow-create
                    @change="onUserModelSelect"
                    style="width: 100%"
                  >
                    <el-option 
                      v-for="model in userAIModels" 
                      :key="model.model_id" 
                      :label="model.model_id" 
                      :value="model.model_id"
                    />
                  </el-select>
                  <div style="font-size: 12px; color: #909399; margin-top: 5px;">选择已保存的模型或手动输入新模型ID</div>
                </el-form-item>
                <el-form-item label="API密钥 (Token)">
                  <el-input
                    v-model="aiSettings.ai_api_key"
                    type="password"
                    placeholder="ms-xxxxxxxx 或从ModelScope获取的Token"
                    show-password
                  />
                </el-form-item>
              </div>

              <!-- 自定义API配置 -->
              <div v-if="aiSettings.ai_provider === 'custom'" class="ai-config-section">
                <el-form-item label="API地址">
                  <el-input
                    v-model="aiSettings.ai_api_url"
                    placeholder="https://api.example.com/v1/chat/completions"
                  />
                </el-form-item>
                <el-form-item label="API密钥">
                  <el-input
                    v-model="aiSettings.ai_api_key"
                    type="password"
                    placeholder="your-api-key"
                    show-password
                  />
                </el-form-item>
                <el-form-item label="模型名称">
                  <el-input
                    v-model="aiSettings.ai_model"
                    placeholder="gpt-4"
                  />
                </el-form-item>
              </div>

              <el-form-item>
                <el-button type="primary" @click="saveAISettings">保存AI设置</el-button>
                <el-button @click="testAIConnection" :loading="aiTestLoading">测试连接</el-button>
              </el-form-item>
            </el-form>
          </el-card>
        </div>

        <!-- 检测系统 -->
        <div v-if="activeMenu === 'detection'" class="page-content">
          <h2 class="page-title">检测系统</h2>
          
          <!-- 检测类型选择 -->
          <el-card v-if="!currentDetectionType" shadow="never" style="margin-bottom: 20px;">
            <div class="detection-modules">
              <el-row :gutter="20">
                <el-col :span="8">
                  <el-card shadow="hover" class="module-card" @click="currentDetectionType = 'image'">
                    <div class="module-icon detection-icon">
                      <el-icon :size="48"><Picture /></el-icon>
                    </div>
                    <h3 class="module-title">图片检测</h3>
                    <p class="module-desc">上传X光片进行骨折检测分析</p>
                  </el-card>
                </el-col>
                <el-col :span="8">
                  <el-card shadow="hover" class="module-card" @click="currentDetectionType = 'video'">
                    <div class="module-icon video-icon">
                      <el-icon :size="48"><VideoCamera /></el-icon>
                    </div>
                    <h3 class="module-title">视频检测</h3>
                    <p class="module-desc">分析视频流中的骨折情况</p>
                  </el-card>
                </el-col>
                <el-col :span="8">
                  <el-card shadow="hover" class="module-card" @click="currentDetectionType = 'camera'">
                    <div class="module-icon camera-icon">
                      <el-icon :size="48"><Camera /></el-icon>
                    </div>
                    <h3 class="module-title">摄像头检测</h3>
                    <p class="module-desc">实时摄像头骨折检测</p>
                  </el-card>
                </el-col>
              </el-row>
            </div>
          </el-card>
          
          <!-- 检测历史记录列表 -->
          <el-card v-if="!currentDetectionType" shadow="never">
            <template #header>
              <div class="card-header">
                <span>图片检测历史记录</span>
                <el-button :icon="Refresh" circle size="small" @click="fetchDetectionHistory" title="刷新" />
              </div>
            </template>

            <el-table :data="detectionHistoryList" v-loading="detectionHistoryLoading" stripe>
              <el-table-column prop="id" label="ID" width="60" />
              <el-table-column prop="filename" label="文件名" min-width="150" show-overflow-tooltip />
              <el-table-column prop="patient_name" label="患者" width="120">
                <template #default="{ row }">
                  <span v-if="row.patient_name">{{ row.patient_name }}</span>
                  <span v-else style="color: #909399;">-</span>
                </template>
              </el-table-column>
              <el-table-column prop="doctor_name" label="检测医生" width="120">
                <template #default="{ row }">
                  <span v-if="row.doctor_name">{{ row.doctor_name }}</span>
                  <span v-else style="color: #909399;">-</span>
                </template>
              </el-table-column>
              <el-table-column prop="timestamp" label="检测时间" width="180" />
              <el-table-column prop="model" label="使用模型" width="100" />
              <el-table-column label="检测结果" min-width="200">
                <template #default="{ row }">
                  <div v-if="row.detections && row.detections.length > 0">
                    <el-tag
                      v-for="(det, idx) in row.detections.slice(0, 3)"
                      :key="idx"
                      size="small"
                      style="margin-right: 4px; margin-bottom: 2px;"
                      :type="det.confidence > 0.8 ? 'danger' : det.confidence > 0.6 ? 'warning' : 'info'"
                    >
                      {{ det.class }} ({{ (det.confidence * 100).toFixed(1) }}%)
                    </el-tag>
                    <span v-if="row.detections.length > 3" style="color: #909399; font-size: 12px;">
                      +{{ row.detections.length - 3 }} 更多
                    </span>
                  </div>
                  <span v-else style="color: #909399;">未检测到目标</span>
                </template>
              </el-table-column>
              <el-table-column prop="count" label="检测数" width="80" align="center" />
              <el-table-column label="置信度" width="100" align="center">
                <template #default="{ row }">
                  <el-progress
                    :percentage="Math.round(row.confidence * 100)"
                    :color="getConfidenceColor(row.confidence)"
                    :stroke-width="8"
                    :show-text="true"
                  />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="150" fixed="right">
                <template #default="{ row }">
                  <el-button type="primary" size="small" link @click="viewDetectionDetail(row)">
                    查看
                  </el-button>
                  <el-button type="danger" size="small" link @click="deleteDetectionHistory(row)">
                    删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>

            <el-empty v-if="!detectionHistoryLoading && detectionHistoryList.length === 0" description="暂无图片检测历史记录" />
          </el-card>

          <!-- 检测详情对话框 -->
          <el-dialog
            v-model="detectionDetailVisible"
            title="检测详情"
            width="800px"
            :close-on-click-modal="false"
          >
            <div v-if="selectedDetection" class="detection-detail">
              <!-- 图片对比 -->
              <el-row :gutter="20" style="margin-bottom: 20px;">
                <el-col :span="12">
                  <div class="image-card">
                    <div class="image-title">原始图片</div>
                    <div class="image-wrapper">
                      <el-image
                        :src="selectedDetection.original_image"
                        fit="contain"
                        :preview-src-list="[selectedDetection.original_image, selectedDetection.result_image]"
                      />
                    </div>
                  </div>
                </el-col>
                <el-col :span="12">
                  <div class="image-card">
                    <div class="image-title">检测结果</div>
                    <div class="image-wrapper">
                      <el-image
                        :src="selectedDetection.result_image"
                        fit="contain"
                        :preview-src-list="[selectedDetection.result_image, selectedDetection.original_image]"
                      />
                    </div>
                  </div>
                </el-col>
              </el-row>

              <!-- 基本信息 -->
              <el-descriptions :column="2" border>
                <el-descriptions-item label="ID">{{ selectedDetection.id }}</el-descriptions-item>
                <el-descriptions-item label="文件名">{{ selectedDetection.filename }}</el-descriptions-item>
                <el-descriptions-item label="患者">{{ selectedDetection.patient_name || '-' }}</el-descriptions-item>
                <el-descriptions-item label="检测医生">{{ selectedDetection.doctor_name || '-' }}</el-descriptions-item>
                <el-descriptions-item label="检测时间">{{ selectedDetection.timestamp }}</el-descriptions-item>
                <el-descriptions-item label="使用模型">{{ selectedDetection.model }}</el-descriptions-item>
                <el-descriptions-item label="检测数量">{{ selectedDetection.count }}</el-descriptions-item>
                <el-descriptions-item label="平均置信度">
                  <el-progress
                    :percentage="Math.round(selectedDetection.confidence * 100)"
                    :color="getConfidenceColor(selectedDetection.confidence)"
                    style="width: 150px;"
                  />
                </el-descriptions-item>
              </el-descriptions>

              <!-- 检测结果详情 -->
              <div v-if="selectedDetection.detections && selectedDetection.detections.length > 0" style="margin-top: 20px;">
                <h4>检测详情</h4>
                <el-table :data="selectedDetection.detections" border size="small">
                  <el-table-column type="index" label="序号" width="60" align="center" />
                  <el-table-column prop="class" label="类型" width="150" />
                  <el-table-column label="置信度" width="200">
                    <template #default="{ row }">
                      <el-progress
                        :percentage="Math.round(row.confidence * 100)"
                        :color="getConfidenceColor(row.confidence)"
                        :stroke-width="10"
                      />
                    </template>
                  </el-table-column>
                  <el-table-column prop="bbox" label="检测框坐标" min-width="200" />
                </el-table>
              </div>

              <!-- 医疗建议 -->
              <div v-if="selectedDetection.medical_advice" style="margin-top: 20px;">
                <h4>医疗建议</h4>
                <el-alert type="info" :closable="false">
                  <div v-if="typeof selectedDetection.medical_advice === 'object'">
                    <div v-if="selectedDetection.medical_advice.interpretation" class="markdown-body medical-advice-content">
                      <vue-markdown :source="selectedDetection.medical_advice.interpretation" />
                    </div>
                    <div v-else>
                      <p v-if="selectedDetection.medical_advice.diagnosis"><strong>AI诊断：</strong>{{ selectedDetection.medical_advice.diagnosis }}</p>
                      <p v-if="selectedDetection.medical_advice.treatment"><strong>治疗建议：</strong>{{ selectedDetection.medical_advice.treatment }}</p>
                      <p v-if="selectedDetection.medical_advice.precautions"><strong>注意事项：</strong>{{ selectedDetection.medical_advice.precautions }}</p>
                    </div>
                  </div>
                  <div v-else class="markdown-body medical-advice-content">
                    <vue-markdown :source="selectedDetection.medical_advice" />
                  </div>
                </el-alert>
              </div>
            </div>
            <template #footer>
              <el-button @click="detectionDetailVisible = false">关闭</el-button>
            </template>
          </el-dialog>

          <!-- 返回按钮 -->
          <div v-if="currentDetectionType" style="margin-bottom: 16px;">
            <el-button @click="currentDetectionType = null">
              <el-icon><ArrowLeft /></el-icon> 返回检测选择
            </el-button>
          </div>
          
          <!-- 图片检测 -->
          <div v-if="currentDetectionType === 'image'" class="detection-content">
            <Detection />
          </div>
          
          <!-- 视频检测 -->
          <div v-if="currentDetectionType === 'video'" class="detection-content">
            <VideoStreamDetection />
          </div>
          
          <!-- 摄像头检测 -->
          <div v-if="currentDetectionType === 'camera'" class="detection-content">
            <CameraDetection />
          </div>
        </div>

        <!-- 模型训练 -->
        <div v-if="activeMenu === 'training'" class="page-content">
          <h2 class="page-title">模型训练</h2>
          
          <!-- 训练配置卡片 -->
          <el-card shadow="never" class="training-card" style="margin-bottom: 20px;">
            <template #header>
              <div class="card-header">
                <span>训练配置</span>
              </div>
            </template>
            
            <el-form :model="trainingForm" label-width="120px" ref="trainingFormRef">
              <el-row :gutter="20">
                <el-col :span="12">
                  <el-form-item label="模型名称" required>
                    <el-input v-model="trainingForm.name" placeholder="请输入模型名称" maxlength="50" show-word-limit />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="基础模型" required>
                    <el-select v-model="trainingForm.base_model" style="width: 100%" placeholder="选择基础模型">
                      <el-option label="YOLOv8" value="yolov8" />
                      <el-option label="YOLO11" value="yolo11" />
                      <el-option label="YOLOv5" value="yolo26" />
                      <el-option-group label="自定义模型（续训）" v-if="availableCustomModels.length > 0">
                        <el-option 
                          v-for="model in availableCustomModels" 
                          :key="model.id" 
                          :label="model.name" 
                          :value="model.id"
                        />
                      </el-option-group>
                    </el-select>
                  </el-form-item>
                </el-col>
              </el-row>
              
              <el-form-item label="模型描述">
                <el-input 
                  v-model="trainingForm.description" 
                  type="textarea" 
                  :rows="2" 
                  placeholder="请输入模型描述"
                  maxlength="200"
                  show-word-limit
                />
              </el-form-item>
              
              <el-row :gutter="20">
                <el-col :span="8">
                  <el-form-item label="训练轮数">
                    <el-input-number v-model="trainingForm.epochs" :min="10" :max="500" :step="10" style="width: 100%" />
                  </el-form-item>
                </el-col>
                <el-col :span="8">
                  <el-form-item label="批次大小">
                    <el-input-number v-model="trainingForm.batch_size" :min="1" :max="64" :step="1" style="width: 100%" />
                  </el-form-item>
                </el-col>
                <el-col :span="8">
                  <el-form-item label="图像尺寸">
                    <el-select v-model="trainingForm.img_size" style="width: 100%">
                      <el-option label="640x640" :value="640" />
                      <el-option label="1280x1280" :value="1280" />
                    </el-select>
                  </el-form-item>
                </el-col>
              </el-row>
              
              <el-form-item label="数据集来源">
                <el-radio-group v-model="datasetSource">
                  <el-radio label="existing">使用现有数据集</el-radio>
                  <el-radio label="upload">上传新数据集</el-radio>
                </el-radio-group>
              </el-form-item>
              
              <el-form-item label="选择数据集" v-if="datasetSource === 'existing'" required>
                <el-select v-model="trainingForm.dataset_id" style="width: 100%" placeholder="请选择数据集">
                  <el-option 
                    v-for="ds in availableDatasets" 
                    :key="ds.id" 
                    :label="ds.name + ' (' + ds.image_count + '张图片)'" 
                    :value="ds.id"
                  />
                </el-select>
                <div v-if="selectedDatasetInfo" style="margin-top: 8px; color: #666; font-size: 12px;">
                  数据集信息: {{ selectedDatasetInfo.description || '无描述' }} | 
                  类别: {{ selectedDatasetInfo.classes?.join(', ') || '未知' }}
                </div>
              </el-form-item>
              
              <el-form-item label="上传数据集" v-else required>
                <el-upload
                  ref="uploadRef"
                  action="#"
                  :auto-upload="false"
                  :on-change="onDatasetChange"
                  :limit="1"
                  accept=".zip,.tar,.gz"
                >
                  <el-button type="primary">
                    <el-icon><Upload /></el-icon> 选择文件
                  </el-button>
                  <template #tip>
                    <div class="el-upload__tip">
                      请上传包含 images 和 labels 文件夹的数据集压缩包 (ZIP格式)
                    </div>
                  </template>
                </el-upload>
              </el-form-item>
              
              <el-form-item>
                <el-checkbox v-model="trainingForm.use_best_hyperparams">使用推荐超参数</el-checkbox>
              </el-form-item>
              
              <el-form-item>
                <el-button 
                  type="primary" 
                  size="large" 
                  @click="startTraining" 
                  :loading="isTraining"
                  :disabled="!canStartTraining"
                >
                  <el-icon><VideoPlay /></el-icon>
                  {{ isTraining ? '训练中...' : '开始训练' }}
                </el-button>
                <el-button size="large" @click="resetTrainingForm">重置</el-button>
              </el-form-item>
            </el-form>
          </el-card>
          
          <!-- 训练任务列表 -->
          <el-card shadow="never" class="tasks-card" style="margin-bottom: 20px;">
            <template #header>
              <div class="card-header">
                <span>训练任务</span>
                <el-button link @click="loadTrainingTasks">
                  <el-icon><Refresh /></el-icon> 刷新
                </el-button>
              </div>
            </template>
            
            <el-table :data="trainingTasks" style="width: 100%" v-loading="tasksLoading">
              <el-table-column prop="name" label="任务名称" min-width="150" show-overflow-tooltip />
              <el-table-column prop="base_model" label="基础模型" width="120" />
              <el-table-column prop="status" label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="getTaskStatusType(row.status)">
                    {{ getTaskStatusText(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="progress" label="进度" width="150">
                <template #default="{ row }">
                  <el-progress 
                    :percentage="Math.round((row.current_epoch || 0) / (row.total_epochs || 1) * 100)" 
                    :status="row.status === 'failed' ? 'exception' : ''"
                  />
                </template>
              </el-table-column>
              <el-table-column prop="created_at" label="创建时间" width="160">
                <template #default="{ row }">
                  {{ formatDateTime(row.created_at) }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="200" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" @click="viewTaskDetail(row)">详情</el-button>
                  <el-button link type="primary" @click="viewTaskLogs(row)">日志</el-button>
                  <el-button link type="danger" v-if="row.status === 'running'" @click="stopTrainingTask(row)">终止</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
          
          <!-- 模型库 -->
          <el-card shadow="never" class="models-card">
            <template #header>
              <div class="card-header">
                <span>模型库</span>
                <div>
                  <el-radio-group v-model="modelFilter" size="small" style="margin-right: 10px;">
                    <el-radio-button label="all">全部</el-radio-button>
                    <el-radio-button label="system">系统模型</el-radio-button>
                    <el-radio-button label="custom">自定义模型</el-radio-button>
                  </el-radio-group>
                  <el-button link @click="loadTrainingModels">
                    <el-icon><Refresh /></el-icon> 刷新
                  </el-button>
                </div>
              </div>
            </template>
            
            <el-table :data="filteredTrainingModels" style="width: 100%" v-loading="modelsLoading">
              <el-table-column prop="name" label="模型名称" min-width="150" show-overflow-tooltip />
              <el-table-column prop="type" label="类型" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.type === 'system' ? 'info' : 'success'">
                    {{ row.type === 'system' ? '系统' : '自定义' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="status" label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="getModelStatusType(row.status)">
                    {{ getModelStatusText(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="map50" label="mAP" width="100">
                <template #default="{ row }">
                  <span v-if="row.map50" :style="{ color: getMetricColor(row.map50) }">
                    {{ (row.map50 * 100).toFixed(1) }}%
                  </span>
                  <span v-else>-</span>
                </template>
              </el-table-column>
              <el-table-column prop="created_at" label="创建时间" width="160">
                <template #default="{ row }">
                  {{ formatDateTime(row.created_at) }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="250" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" @click="viewModelDetail(row)">详情</el-button>
                  <el-button link type="success" v-if="row.status === 'trained'" @click="publishTrainingModel(row)">发布</el-button>
                  <el-button link type="warning" v-if="row.status === 'published'" @click="disableTrainingModel(row)">禁用</el-button>
                  <el-button link type="primary" v-if="row.status === 'disabled'" @click="enableTrainingModel(row)">启用</el-button>
                  <el-button link type="danger" v-if="row.type === 'custom'" @click="deleteTrainingModel(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
          
          <!-- 任务详情弹窗 -->
          <el-dialog v-model="taskDetailVisible" title="任务详情" width="600px">
            <div v-if="selectedTask">
              <el-descriptions :column="2" border>
                <el-descriptions-item label="任务名称">{{ selectedTask.name }}</el-descriptions-item>
                <el-descriptions-item label="基础模型">{{ selectedTask.base_model }}</el-descriptions-item>
                <el-descriptions-item label="状态">
                  <el-tag :type="getTaskStatusType(selectedTask.status)">
                    {{ getTaskStatusText(selectedTask.status) }}
                  </el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="进度">
                  {{ selectedTask.current_epoch || 0 }} / {{ selectedTask.total_epochs || 0 }} 轮
                </el-descriptions-item>
                <el-descriptions-item label="创建时间">{{ formatDateTime(selectedTask.created_at) }}</el-descriptions-item>
                <el-descriptions-item label="完成时间">
                  {{ selectedTask.completed_at ? formatDateTime(selectedTask.completed_at) : '-' }}
                </el-descriptions-item>
              </el-descriptions>
              
              <div v-if="selectedTask.metrics" style="margin-top: 20px;">
                <h4>训练指标</h4>
                <el-row :gutter="20" style="margin-top: 10px;">
                  <el-col :span="8">
                    <div class="metric-item">
                      <div class="metric-value" :style="{ color: getMetricColor(selectedTask.metrics.map50) }">
                        {{ selectedTask.metrics.map50 ? (selectedTask.metrics.map50 * 100).toFixed(1) + '%' : '-' }}
                      </div>
                      <div class="metric-label">mAP@0.5</div>
                    </div>
                  </el-col>
                  <el-col :span="8">
                    <div class="metric-item">
                      <div class="metric-value" :style="{ color: getMetricColor(selectedTask.metrics.map50_95) }">
                        {{ selectedTask.metrics.map50_95 ? (selectedTask.metrics.map50_95 * 100).toFixed(1) + '%' : '-' }}
                      </div>
                      <div class="metric-label">mAP@0.5:0.95</div>
                    </div>
                  </el-col>
                  <el-col :span="8">
                    <div class="metric-item">
                      <div class="metric-value">{{ selectedTask.metrics.precision ? (selectedTask.metrics.precision * 100).toFixed(1) + '%' : '-' }}</div>
                      <div class="metric-label">Precision</div>
                    </div>
                  </el-col>
                </el-row>
              </div>
            </div>
          </el-dialog>
          
          <!-- 训练日志弹窗 -->
          <el-dialog v-model="logsVisible" title="训练日志" width="800px">
            <div class="log-container">
              <pre style="background: #1e1e1e; color: #d4d4d4; padding: 16px; border-radius: 4px; overflow-x: auto; max-height: 500px; font-size: 12px; line-height: 1.6;">{{ trainingLogs || '暂无日志' }}</pre>
            </div>
          </el-dialog>
          
          <!-- 模型详情弹窗 -->
          <el-dialog v-model="modelDetailVisible" title="模型详情" width="600px">
            <div v-if="selectedModel">
              <el-descriptions :column="1" border>
                <el-descriptions-item label="模型名称">{{ selectedModel.name }}</el-descriptions-item>
                <el-descriptions-item label="模型描述">{{ selectedModel.description || '无描述' }}</el-descriptions-item>
                <el-descriptions-item label="基础模型">{{ selectedModel.base_model }}</el-descriptions-item>
                <el-descriptions-item label="类型">
                  <el-tag :type="selectedModel.type === 'system' ? 'info' : 'success'">
                    {{ selectedModel.type === 'system' ? '系统模型' : '自定义模型' }}
                  </el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="状态">
                  <el-tag :type="getModelStatusType(selectedModel.status)">
                    {{ getModelStatusText(selectedModel.status) }}
                  </el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="创建时间">{{ formatDateTime(selectedModel.created_at) }}</el-descriptions-item>
              </el-descriptions>
              
              <div v-if="selectedModel.metrics" style="margin-top: 20px;">
                <h4>模型性能指标</h4>
                <el-descriptions :column="2" border style="margin-top: 10px;">
                  <el-descriptions-item label="mAP@0.5">
                    <span :style="{ color: getMetricColor(selectedModel.metrics.map50) }">
                      {{ selectedModel.metrics.map50 ? (selectedModel.metrics.map50 * 100).toFixed(1) + '%' : '-' }}
                    </span>
                  </el-descriptions-item>
                  <el-descriptions-item label="mAP@0.5:0.95">
                    <span :style="{ color: getMetricColor(selectedModel.metrics.map50_95) }">
                      {{ selectedModel.metrics.map50_95 ? (selectedModel.metrics.map50_95 * 100).toFixed(1) + '%' : '-' }}
                    </span>
                  </el-descriptions-item>
                  <el-descriptions-item label="Precision">{{ selectedModel.metrics.precision ? (selectedModel.metrics.precision * 100).toFixed(1) + '%' : '-' }}</el-descriptions-item>
                  <el-descriptions-item label="Recall">{{ selectedModel.metrics.recall ? (selectedModel.metrics.recall * 100).toFixed(1) + '%' : '-' }}</el-descriptions-item>
                </el-descriptions>
              </div>
            </div>
          </el-dialog>
        </div>

        <!-- 数据分析 -->
        <div v-if="activeMenu === 'analysis'" class="page-content">
          <h2 class="page-title">数据分析</h2>
          
          <!-- 核心指标卡片 -->
          <el-row :gutter="20" style="margin-bottom: 20px;">
            <el-col :span="6">
              <el-card class="stat-card" shadow="hover">
                <div class="stat-icon" style="background: #e6f7ff; color: #1890ff;">
                  <el-icon :size="24"><Camera /></el-icon>
                </div>
                <div class="stat-value">{{ analysisData.total_detections || 0 }}</div>
                <div class="stat-label">总检测次数</div>
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card class="stat-card" shadow="hover">
                <div class="stat-icon" style="background: #f6ffed; color: #52c41a;">
                  <el-icon :size="24"><MagicStick /></el-icon>
                </div>
                <div class="stat-value">{{ analysisData.models_used ? Object.keys(analysisData.models_used).length : 0 }}</div>
                <div class="stat-label">使用模型数</div>
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card class="stat-card" shadow="hover">
                <div class="stat-icon" style="background: #fff7e6; color: #fa8c16;">
                  <el-icon :size="24"><Collection /></el-icon>
                </div>
                <div class="stat-value">{{ analysisData.classes_detected ? Object.keys(analysisData.classes_detected).length : 0 }}</div>
                <div class="stat-label">检测类别数</div>
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card class="stat-card" shadow="hover">
                <div class="stat-icon" style="background: #f9f0ff; color: #722ed1;">
                  <el-icon :size="24"><TrendCharts /></el-icon>
                </div>
                <div class="stat-value">{{ ((analysisData.avg_confidence || 0) * 100).toFixed(1) }}%</div>
                <div class="stat-label">平均置信度</div>
              </el-card>
            </el-col>
          </el-row>

          <!-- 模型使用分布 -->
          <el-card shadow="never" style="margin-bottom: 20px;">
            <template #header>
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>模型使用分布</span>
                <el-tag size="small" type="info">按检测次数</el-tag>
              </div>
            </template>
            <div v-if="analysisData.models_used && Object.keys(analysisData.models_used).length > 0">
              <div v-for="(count, model) in analysisData.models_used" :key="model" style="margin-bottom: 16px;">
                <div style="font-size: 14px; color: #1e293b; margin-bottom: 8px; font-weight: 500;">{{ getModelDisplayName(model) }}</div>
                <el-progress 
                  :percentage="Math.round((count / analysisData.total_detections) * 100)" 
                  :format="() => count + '次'"
                />
              </div>
            </div>
            <el-empty v-else description="暂无模型使用数据" />
          </el-card>

          <!-- 检测类别分布 -->
          <el-card shadow="never" style="margin-bottom: 20px;">
            <template #header>
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>检测类别分布</span>
                <el-tag size="small" type="info">按检测次数</el-tag>
              </div>
            </template>
            <div v-if="analysisData.classes_detected && Object.keys(analysisData.classes_detected).length > 0">
              <!-- 环形图 -->
              <div style="display: flex; align-items: center; gap: 40px; padding: 20px;">
                <!-- 左侧：环形图 -->
                <div class="donut-chart-container">
                  <svg viewBox="0 0 200 200" class="donut-chart">
                    <circle cx="100" cy="100" r="80" fill="none" stroke="#f0f0f0" stroke-width="30"/>
                    <circle 
                      v-for="(segment, index) in classChartData" 
                      :key="index"
                      cx="100" 
                      cy="100" 
                      r="80" 
                      fill="none" 
                      :stroke="segment.color"
                      stroke-width="30"
                      :stroke-dasharray="segment.dashArray"
                      :stroke-dashoffset="segment.dashOffset"
                      transform="rotate(-90 100 100)"
                    />
                    <text x="100" y="95" text-anchor="middle" style="font-size: 24px; font-weight: bold; fill: #1e293b;">
                      {{ Object.keys(analysisData.classes_detected).length }}
                    </text>
                    <text x="100" y="115" text-anchor="middle" style="font-size: 12px; fill: #64748b;">检测类别</text>
                  </svg>
                </div>
                <!-- 右侧：图例和列表 -->
                <div style="flex: 1;">
                  <div v-for="(count, cls) in analysisData.classes_detected" :key="cls" style="display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #f0f0f0;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                      <div :style="{ width: '12px', height: '12px', borderRadius: '50%', background: getClassColor(cls) }"></div>
                      <span style="font-size: 14px; color: #1e293b;">{{ cls }}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 12px;">
                      <span style="font-size: 12px; color: #64748b;">{{ Math.round((count / getTotalClassesCount()) * 100) }}%</span>
                      <el-tag :type="count > 5 ? 'danger' : count > 2 ? 'warning' : 'success'" size="small">
                        {{ count }} 次
                      </el-tag>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <el-empty v-else description="暂无类别检测数据" />
          </el-card>

          <!-- 置信度分析 -->
          <el-card shadow="never" style="margin-bottom: 20px;">
            <template #header>
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>置信度分析</span>
                <el-tag size="small" :type="analysisData.avg_confidence >= 0.8 ? 'success' : analysisData.avg_confidence >= 0.5 ? 'warning' : 'danger'">
                  {{ analysisData.avg_confidence >= 0.8 ? '高置信度' : analysisData.avg_confidence >= 0.5 ? '中等置信度' : '低置信度' }}
                </el-tag>
              </div>
            </template>
            <div style="text-align: center; padding: 30px;">
              <div style="font-size: 48px; font-weight: 700; margin-bottom: 8px;" :style="{ color: analysisData.avg_confidence >= 0.8 ? '#52c41a' : analysisData.avg_confidence >= 0.5 ? '#faad14' : '#f5222d' }">
                {{ ((analysisData.avg_confidence || 0) * 100).toFixed(1) }}%
              </div>
              <div style="font-size: 14px; color: #64748b;">平均置信度</div>
              <el-progress 
                :percentage="(analysisData.avg_confidence || 0) * 100" 
                :color="analysisData.avg_confidence >= 0.8 ? '#52c41a' : analysisData.avg_confidence >= 0.5 ? '#faad14' : '#f5222d'"
                :stroke-width="20"
                style="margin-top: 20px;"
              />
            </div>
          </el-card>

          <!-- 检测趋势 -->
          <el-card shadow="never">
            <template #header>
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>检测趋势</span>
                <el-radio-group v-model="trendPeriod" size="small" @change="loadTrendData">
                  <el-radio-button label="week">近7天</el-radio-button>
                  <el-radio-button label="month">近30天</el-radio-button>
                  <el-radio-button label="year">近一年</el-radio-button>
                </el-radio-group>
              </div>
            </template>
            <div style="padding: 20px;">
              <div v-if="trendData.length > 0" style="display: flex; align-items: flex-end; justify-content: space-around; height: 200px; gap: 8px;">
                <div v-for="(item, index) in trendData" :key="index" style="flex: 1; display: flex; flex-direction: column; align-items: center; gap: 8px;">
                  <div style="font-size: 12px; color: #1e293b; font-weight: 600;">{{ item.count }}</div>
                  <div style="width: 100%; height: 150px; display: flex; align-items: flex-end; justify-content: center;">
                    <div style="width: 60%; border-radius: 4px 4px 0 0; transition: all 0.3s ease;" :style="{ height: (item.count / maxTrendCount * 100) + '%', background: item.count === 0 ? '#e8e8e8' : item.count >= 10 ? '#52c41a' : item.count >= 5 ? '#1890ff' : '#faad14' }"></div>
                  </div>
                  <div style="font-size: 12px; color: #64748b; text-align: center;">{{ item.date }}</div>
                </div>
              </div>
              <el-empty v-else description="暂无趋势数据" />
            </div>
          </el-card>
        </div>

        <!-- 统计分析 -->
        <div v-if="activeMenu === 'statistics'" class="page-content">
          <h2 class="page-title">统计分析</h2>
          
          <!-- 日期筛选 -->
          <el-card shadow="never" style="margin-bottom: 20px;">
            <template #header>
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>数据筛选</span>
              </div>
            </template>
            <div style="display: flex; align-items: center; gap: 16px;">
              <span style="color: #606266;">日期范围：</span>
              <el-date-picker
                v-model="statsDateRange"
                type="daterange"
                range-separator="至"
                start-placeholder="开始日期"
                end-placeholder="结束日期"
                style="width: 300px"
                @change="loadPatientStats"
              />
              <el-button type="primary" @click="loadPatientStats">
                <el-icon><Search /></el-icon>
                刷新数据
              </el-button>
            </div>
          </el-card>
          
          <!-- 核心统计指标 -->
          <el-row :gutter="20" style="margin-bottom: 20px;">
            <el-col :span="6">
              <el-card class="stats-card" shadow="hover">
                <div class="stats-item">
                  <div class="stats-value">{{ patientStats.totalPatients }}</div>
                  <div class="stats-label">总患者数</div>
                </div>
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card class="stats-card" shadow="hover">
                <div class="stats-item">
                  <div class="stats-value">{{ patientStats.totalExaminations }}</div>
                  <div class="stats-label">检查记录数</div>
                </div>
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card class="stats-card" shadow="hover">
                <div class="stats-item">
                  <div class="stats-value">{{ patientStats.positiveCases }}</div>
                  <div class="stats-label">阳性病例数</div>
                </div>
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card class="stats-card" shadow="hover">
                <div class="stats-item">
                  <div class="stats-value">{{ patientStats.positiveRate }}%</div>
                  <div class="stats-label">阳性率</div>
                </div>
              </el-card>
            </el-col>
          </el-row>
          
          <!-- 图表区域 -->
          <el-row :gutter="20" style="margin-bottom: 20px;">
            <el-col :span="8">
              <el-card shadow="never">
                <template #header>
                  <span>骨折类型分布</span>
                </template>
                <div ref="fractureTypeChartRef" style="height: 300px;"></div>
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card shadow="never">
                <template #header>
                  <span>年龄段分布</span>
                </template>
                <div ref="ageChartRef" style="height: 300px;"></div>
              </el-card>
            </el-col>
            <el-col :span="8">
              <el-card shadow="never">
                <template #header>
                  <span>月度检查趋势</span>
                </template>
                <div ref="monthlyChartRef" style="height: 300px;"></div>
              </el-card>
            </el-col>
          </el-row>
          
          <el-row :gutter="20" style="margin-bottom: 20px;">
            <el-col :span="12">
              <el-card shadow="never">
                <template #header>
                  <span>性别分布</span>
                </template>
                <div ref="genderChartRef" style="height: 300px;"></div>
              </el-card>
            </el-col>
            <el-col :span="12">
              <el-card shadow="never">
                <template #header>
                  <span>最近检查记录</span>
                </template>
                <el-table :data="recentExaminations" style="width: 100%" border stripe height="300">
                  <el-table-column prop="id" label="ID" width="60" />
                  <el-table-column prop="patient_name" label="患者姓名" />
                  <el-table-column label="检查日期" width="180">
                    <template #default="{ row }">
                      {{ formatLogTime(row.exam_date) }}
                    </template>
                  </el-table-column>
                  <el-table-column prop="result" label="结果" width="80">
                    <template #default="{ row }">
                      <el-tag :type="(row.detection_result?.has_fracture) ? 'danger' : 'success'" size="small">
                        {{ (row.detection_result?.has_fracture) ? '阳性' : '阴性' }}
                      </el-tag>
                    </template>
                  </el-table-column>
                </el-table>
              </el-card>
            </el-col>
          </el-row>
        </div>

        <!-- 公告管理 -->
        <div v-if="activeMenu === 'announcements'" class="page-content">
          <h2 class="page-title">公告管理</h2>
          <el-card shadow="never">
            <div style="margin-bottom: 20px;">
              <el-button type="primary" @click="openCreateAnnouncement">
                <el-icon><Plus /></el-icon> 发布公告
              </el-button>
            </div>

            <el-table :data="announcements" v-loading="announcementsLoading" style="width: 100%">
              <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
              <el-table-column prop="target_role" label="目标用户" width="100">
                <template #default="{ row }">
                  <el-tag :type="getTargetRoleType(row.target_role)">
                    {{ getTargetRoleLabel(row.target_role) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="priority" label="优先级" width="100">
                <template #default="{ row }">
                  <el-tag :type="getPriorityType(row.priority)">
                    {{ getPriorityLabel(row.priority) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="is_active" label="状态" width="80">
                <template #default="{ row }">
                  <el-tag :type="row.is_active ? 'success' : 'info'">
                    {{ row.is_active ? '启用' : '禁用' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="created_at" label="发布时间" width="160">
                <template #default="{ row }">
                  {{ formatDateTime(row.created_at) }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="200" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" @click="viewAnnouncement(row)">
                    <el-icon><View /></el-icon> 查看
                  </el-button>
                  <el-button link type="primary" @click="editAnnouncement(row)">
                    <el-icon><Edit /></el-icon> 编辑
                  </el-button>
                  <el-button link type="danger" @click="deleteAnnouncement(row)">
                    <el-icon><Delete /></el-icon> 删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </div>

        <!-- 数据集管理 -->
        <div v-if="activeMenu === 'datasets'" class="page-content">
          <h2 class="page-title">数据集管理</h2>
          <el-card shadow="never">
            <div style="margin-bottom: 20px;">
              <el-button type="primary" @click="showDatasetUploadDialog = true">
                <el-icon><Upload /></el-icon> 上传数据集
              </el-button>
              <span style="margin-left: 12px; color: #909399; font-size: 12px">
                支持: zip格式数据集（包含data.yaml、images、labels目录）
              </span>
            </div>

            <el-table :data="datasetList" style="width: 100%" v-loading="datasetsLoading" border>
              <el-table-column prop="id" label="ID" width="60" />
              <el-table-column prop="name" label="数据集名称" min-width="150" show-overflow-tooltip />
              <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
              <el-table-column label="数据信息" width="150">
                <template #default="{ row }">
                  <div style="font-size: 12px">
                    <div>图片: {{ row.num_images }}张</div>
                    <div>类别: {{ row.num_classes }}个</div>
                  </div>
                </template>
              </el-table-column>
              <el-table-column prop="size_str" label="大小" width="100" />
              <el-table-column prop="uploader" label="上传者" width="100" />
              <el-table-column label="上传时间" width="160">
                <template #default="{ row }">
                  {{ formatDateTime(row.created_at) }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="200" fixed="right" align="center">
                <template #default="{ row }">
                  <el-button type="primary" size="small" @click="editDataset(row)">编辑</el-button>
                  <el-button type="danger" size="small" @click="deleteDataset(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>

            <el-pagination
              v-model="datasetPagination.page"
              :page-size="datasetPagination.per_page"
              :total="datasetPagination.total"
              :page-sizes="[10, 20, 50]"
              layout="total, sizes, prev, pager, next, jumper"
              style="margin-top: 16px; justify-content: flex-end"
              @size-change="handleDatasetSizeChange"
              @current-change="handleDatasetPageChange"
            />
          </el-card>
        </div>
      </el-main>
    </el-container>

    <!-- 数据集上传弹窗 -->
    <el-dialog
      v-model="showDatasetUploadDialog"
      title="上传数据集"
      width="550px"
      :close-on-click-modal="false"
    >
      <el-form :model="datasetUploadForm" label-width="100px" label-position="top">
        <el-form-item label="数据集名称" required>
          <el-input 
            v-model="datasetUploadForm.name" 
            placeholder="请输入数据集名称，例如：骨折检测数据集v1"
            size="large"
          />
        </el-form-item>
        
        <el-form-item label="数据集描述">
          <el-input
            v-model="datasetUploadForm.description"
            type="textarea"
            :rows="3"
            placeholder="请输入数据集描述，例如：包含1000张骨折X光片，用于训练骨折检测模型"
          />
        </el-form-item>
        
        <el-form-item label="数据集文件" required>
          <el-upload
            ref="datasetUploadRef"
            action="/api/datasets"
            :headers="datasetUploadHeaders"
            :data="datasetUploadForm"
            :on-success="handleDatasetUploadSuccess"
            :on-error="handleDatasetUploadError"
            :before-upload="beforeDatasetUpload"
            :auto-upload="false"
            accept=".zip"
            drag
            style="width: 100%"
          >
            <el-icon class="el-icon--upload" style="font-size: 48px; color: #409EFF; margin-bottom: 10px"><upload-filled /></el-icon>
            <div class="el-upload__text">
              <em>点击上传</em> 或 <em>拖拽文件到此处</em>
            </div>
            <template #tip>
              <div class="el-upload__tip" style="margin-top: 15px; line-height: 1.6">
                <el-alert
                  title="数据集格式要求"
                  type="info"
                  :closable="false"
                  description="请上传zip格式的数据集文件，需包含以下内容：
                  • data.yaml - 数据集配置文件
                  • train/images/ - 训练图片目录
                  • train/labels/ - 训练标注目录
                  • val/images/ - 验证图片目录  
                  • val/labels/ - 验证标注目录"
                  show-icon
                />
              </div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDatasetUploadDialog = false">取消</el-button>
        <el-button type="primary" @click="submitDatasetUpload" size="large">开始上传</el-button>
      </template>
    </el-dialog>

    <!-- 数据集编辑弹窗 -->
    <el-dialog
      v-model="showDatasetEditDialog"
      title="编辑数据集"
      width="550px"
      :close-on-click-modal="false"
    >
      <el-form :model="datasetEditForm" label-width="100px" label-position="top">
        <el-form-item label="数据集名称" required>
          <el-input 
            v-model="datasetEditForm.name" 
            placeholder="请输入数据集名称"
            size="large"
          />
        </el-form-item>
        <el-form-item label="数据集描述">
          <el-input
            v-model="datasetEditForm.description"
            type="textarea"
            :rows="4"
            placeholder="请输入数据集描述"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDatasetEditDialog = false">取消</el-button>
        <el-button type="primary" @click="submitDatasetEdit" size="large">保存修改</el-button>
      </template>
    </el-dialog>

    <!-- 公告编辑/创建弹窗 -->
    <el-dialog
      v-model="showAnnouncementDialog"
      :title="editingAnnouncement ? '编辑公告' : '发布公告'"
      width="600px"
    >
      <el-form :model="announcementForm" label-width="80px">
        <el-form-item label="标题" required>
          <el-input v-model="announcementForm.title" placeholder="请输入公告标题" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item label="内容" required>
          <el-input
            v-model="announcementForm.content"
            type="textarea"
            :rows="6"
            placeholder="请输入公告内容"
            maxlength="2000"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="目标用户">
          <el-select v-model="announcementForm.target_role" style="width: 100%">
            <el-option label="全部用户" value="all" />
            <el-option label="仅患者" value="patient" />
            <el-option label="仅医生" value="doctor" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="announcementForm.priority" style="width: 100%">
            <el-option label="普通" value="normal" />
            <el-option label="低" value="low" />
            <el-option label="高" value="high" />
            <el-option label="紧急" value="urgent" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" v-if="editingAnnouncement">
          <el-switch
            v-model="announcementForm.is_active"
            active-text="启用"
            inactive-text="禁用"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAnnouncementDialog = false">取消</el-button>
        <el-button type="primary" :loading="announcementSubmitting" @click="submitAnnouncement">
          {{ editingAnnouncement ? '保存' : '发布' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 公告查看弹窗 -->
    <el-dialog v-model="showViewDialog" title="公告详情" width="600px">
      <div v-if="viewingAnnouncement">
        <h3 style="margin-bottom: 16px;">{{ viewingAnnouncement.title }}</h3>
        <div style="margin-bottom: 16px;">
          <el-tag :type="getTargetRoleType(viewingAnnouncement.target_role)" style="margin-right: 8px;">
            {{ getTargetRoleLabel(viewingAnnouncement.target_role) }}
          </el-tag>
          <el-tag :type="getPriorityType(viewingAnnouncement.priority)" style="margin-right: 8px;">
            {{ getPriorityLabel(viewingAnnouncement.priority) }}
          </el-tag>
          <el-tag :type="viewingAnnouncement.is_active ? 'success' : 'info'">
            {{ viewingAnnouncement.is_active ? '启用' : '禁用' }}
          </el-tag>
        </div>
        <div style="color: #999; font-size: 14px; margin-bottom: 16px;">
          发布时间：{{ formatDateTime(viewingAnnouncement.created_at) }}
        </div>
        <div style="line-height: 1.8; white-space: pre-wrap;">{{ viewingAnnouncement.content }}</div>
      </div>
    </el-dialog>

    <!-- 审核详情弹窗 -->
    <el-dialog v-model="detailVisible" title="医生申请详情" width="600px">
      <el-descriptions :column="2" border v-if="selectedDoctor">
        <el-descriptions-item label="姓名">{{ selectedDoctor.full_name }}</el-descriptions-item>
        <el-descriptions-item label="用户名">{{ selectedDoctor.username }}</el-descriptions-item>
        <el-descriptions-item label="所属医院">{{ selectedDoctor.hospital }}</el-descriptions-item>
        <el-descriptions-item label="科室">{{ selectedDoctor.department }}</el-descriptions-item>
        <el-descriptions-item label="职称">{{ selectedDoctor.title }}</el-descriptions-item>
        <el-descriptions-item label="执业证号">{{ selectedDoctor.license_number }}</el-descriptions-item>
        <el-descriptions-item label="专业特长" :span="2">{{ selectedDoctor.specialty }}</el-descriptions-item>
        <el-descriptions-item label="联系电话">{{ selectedDoctor.phone }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ selectedDoctor.email }}</el-descriptions-item>
      </el-descriptions>
      <template #footer v-if="selectedDoctor?.status === 'pending'">
        <el-input v-model="reviewNote" type="textarea" :rows="2" placeholder="审核备注（可选）" style="margin-bottom: 10px" />
        <div>
          <el-button @click="detailVisible = false">取消</el-button>
          <el-button type="danger" @click="confirmReject">拒绝</el-button>
          <el-button type="success" @click="confirmApprove">通过</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 医生详情弹窗 -->
    <el-dialog v-model="doctorDetailVisible" title="医生详情" width="600px">
      <el-descriptions :column="2" border v-if="selectedDoctorDetail">
        <el-descriptions-item label="姓名">{{ selectedDoctorDetail.full_name }}</el-descriptions-item>
        <el-descriptions-item label="所属医院">{{ selectedDoctorDetail.hospital }}</el-descriptions-item>
        <el-descriptions-item label="科室">{{ selectedDoctorDetail.department }}</el-descriptions-item>
        <el-descriptions-item label="职称">{{ selectedDoctorDetail.title }}</el-descriptions-item>
        <el-descriptions-item label="联系电话">{{ selectedDoctorDetail.phone }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="selectedDoctorDetail.status === 'active' ? 'success' : 'info'">
            {{ selectedDoctorDetail.status === 'active' ? '正常' : '停用' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <!-- 患者详情弹窗 -->
    <el-dialog v-model="patientDetailVisible" title="患者详情" width="600px">
      <el-descriptions :column="2" border v-if="selectedPatientDetail">
        <el-descriptions-item label="姓名">{{ selectedPatientDetail.full_name }}</el-descriptions-item>
        <el-descriptions-item label="病历号">{{ selectedPatientDetail.patient_number }}</el-descriptions-item>
        <el-descriptions-item label="性别">{{ selectedPatientDetail.gender }}</el-descriptions-item>
        <el-descriptions-item label="联系电话">{{ selectedPatientDetail.phone }}</el-descriptions-item>
        <el-descriptions-item label="注册时间">{{ formatDateTime(selectedPatientDetail.created_at) }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <!-- 编辑医生弹窗 -->
    <el-dialog v-model="editDoctorVisible" title="编辑医生信息" width="600px">
      <el-form :model="editingDoctor" label-width="100px">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="真实姓名">
              <el-input v-model="editingDoctor.full_name" placeholder="请输入真实姓名" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="联系电话">
              <el-input v-model="editingDoctor.phone" placeholder="请输入手机号" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="所属医院">
              <el-input v-model="editingDoctor.hospital" placeholder="请输入医院名称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="科室">
              <el-input v-model="editingDoctor.department" placeholder="请输入科室" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="职称">
              <el-select v-model="editingDoctor.title" placeholder="请选择职称" style="width: 100%">
                <el-option label="住院医师" value="住院医师" />
                <el-option label="主治医师" value="主治医师" />
                <el-option label="副主任医师" value="副主任医师" />
                <el-option label="主任医师" value="主任医师" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态">
              <el-select v-model="editingDoctor.status" placeholder="请选择状态" style="width: 100%">
                <el-option label="正常" value="active" />
                <el-option label="停用" value="inactive" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="editDoctorVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingDoctor" @click="saveDoctorEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 编辑患者弹窗 -->
    <el-dialog v-model="editPatientVisible" title="编辑患者信息" width="600px">
      <el-form :model="editingPatient" label-width="100px">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="真实姓名">
              <el-input v-model="editingPatient.full_name" placeholder="请输入真实姓名" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="性别">
              <el-radio-group v-model="editingPatient.gender">
                <el-radio value="男">男</el-radio>
                <el-radio value="女">女</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="联系电话">
              <el-input v-model="editingPatient.phone" placeholder="请输入手机号" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="病历号">
              <el-input v-model="editingPatient.patient_number" placeholder="请输入病历号" disabled />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="editPatientVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingPatient" @click="savePatientEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Setting, DocumentChecked, FirstAidKit, User, Camera, Picture, VideoCamera, MagicStick, TrendCharts, DataAnalysis, Document, Monitor, Collection, Search, Calendar, Bell, Plus, Edit, Delete, View, Upload, VideoPlay, Refresh, Folder, UploadFilled, ArrowLeft } from '@element-plus/icons-vue'
import axios from '../utils/axios'
import * as echarts from 'echarts'
import Detection from './Detection.vue'
import VideoStreamDetection from './VideoStreamDetection.vue'
import CameraDetection from './CameraDetection.vue'
import VueMarkdown from 'vue-markdown-render'
import 'github-markdown-css/github-markdown-light.css'
import { formatDate, formatDateTime } from '../utils/datetime'

const router = useRouter()
const activeMenu = ref('approvals')
const approvalTab = ref('pending')
const adminInfo = ref({})
const pendingApprovals = ref([])
const processedApprovals = ref([])
const doctors = ref([])
const patients = ref([])
const pendingCount = ref(0)
const detailVisible = ref(false)
const selectedDoctor = ref(null)
const reviewNote = ref('')
const doctorDetailVisible = ref(false)
const selectedDoctorDetail = ref(null)
const patientDetailVisible = ref(false)
const selectedPatientDetail = ref(null)
const editDoctorVisible = ref(false)
const editPatientVisible = ref(false)
const editingDoctor = ref({})
const editingPatient = ref({})
const savingDoctor = ref(false)
const savingPatient = ref(false)

// 公告管理相关数据
const announcements = ref([])
const announcementsLoading = ref(false)
const showAnnouncementDialog = ref(false)
const showViewDialog = ref(false)
const editingAnnouncement = ref(null)
const viewingAnnouncement = ref(null)
const announcementSubmitting = ref(false)
const announcementForm = ref({
  title: '',
  content: '',
  target_role: 'all',
  priority: 'normal',
  is_active: true
})

// 数据集管理相关数据
const datasetList = ref([])
const datasetsLoading = ref(false)
const showDatasetUploadDialog = ref(false)
const showDatasetEditDialog = ref(false)
const datasetUploadRef = ref(null)
const datasetPagination = reactive({
  page: 1,
  per_page: 20,
  total: 0
})
const datasetUploadForm = reactive({
  name: '',
  description: ''
})
const datasetEditForm = reactive({
  id: null,
  name: '',
  description: ''
})
const datasetUploadHeaders = computed(() => {
  return {
    'X-Username': localStorage.getItem('username') || ''
  }
})

// 检测系统相关数据
const currentDetectionType = ref(null)

// 检测历史记录相关数据
const detectionHistoryList = ref([])
const detectionHistoryLoading = ref(false)

// 获取检测历史记录列表（只获取图片检测记录）
const fetchDetectionHistory = async () => {
  detectionHistoryLoading.value = true
  try {
    const res = await axios.get('/api/history?image_only=true')
    if (res.data.data) {
      detectionHistoryList.value = res.data.data || []
    }
  } catch (error) {
    console.error('获取检测历史记录失败:', error)
    ElMessage.error('获取检测历史记录失败')
  } finally {
    detectionHistoryLoading.value = false
  }
}

// 查看检测历史记录详情
const selectedDetection = ref(null)
const detectionDetailVisible = ref(false)

const viewDetectionDetail = (row) => {
  selectedDetection.value = row
  detectionDetailVisible.value = true
}

// 删除检测历史记录
const deleteDetectionHistory = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除这条检测历史记录吗？`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    const res = await axios.delete(`/api/history/${row.id}`)
    if (res.data.success) {
      ElMessage.success('删除成功')
      fetchDetectionHistory()
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除检测历史记录失败:', error)
      ElMessage.error('删除失败')
    }
  }
}

// 根据置信度获取颜色
const getConfidenceColor = (confidence) => {
  if (confidence >= 0.8) return '#67c23a'
  if (confidence >= 0.6) return '#e6a23c'
  return '#f56c6c'
}

const systemConfig = reactive({
  name: '智慧骨科云平台',
  captchaTimeout: 5,
  doctorApproval: true
})

// AI设置相关数据
const aiSettings = reactive({
  default_model: 'yolov8',
  available_models: [],
  confidence_threshold: 0.25,
  ai_provider: 'local',
  ai_api_key: '',
  ai_api_url: '',
  ai_model: 'gpt-4'
})
const aiTestLoading = ref(false)
const userAIModels = ref([])

// 计算属性：系统模型列表
const systemModelsForSettings = computed(() => {
  if (!aiSettings.available_models) return []
  return aiSettings.available_models.filter(m => m.type === 'system')
})

// 计算属性：自定义模型列表
const customModelsForSettings = computed(() => {
  if (!aiSettings.available_models) return []
  return aiSettings.available_models.filter(m => m.type === 'custom')
})

// 检测系统、模型训练、数据分析、统计分析相关数据
const trainedModels = ref([])

// 模型训练相关数据
const trainingFormRef = ref(null)
const uploadRef = ref(null)
const isTraining = ref(false)
const modelFilter = ref('all')
const trainingTasks = ref([])
const trainingModels = ref({ system_models: [], custom_models: [] })
const trainingLogs = ref('')
const taskDetailVisible = ref(false)
const logsVisible = ref(false)
const modelDetailVisible = ref(false)
const selectedTask = ref(null)
const selectedModel = ref(null)
const progressTimer = ref(null)
const datasetSource = ref('existing')
const availableDatasets = ref([])
const tasksLoading = ref(false)
const modelsLoading = ref(false)
const trainingForm = reactive({
  name: '',
  description: '',
  base_model: 'yolov8',
  epochs: 100,
  batch_size: 16,
  img_size: 640,
  dataset: null,
  dataset_id: null,
  use_best_hyperparams: false
})

// 计算属性
const canStartTraining = computed(() => {
  if (datasetSource.value === 'existing') {
    return trainingForm.name && trainingForm.dataset_id && !isTraining.value
  } else {
    return trainingForm.name && trainingForm.dataset && !isTraining.value
  }
})

const selectedDatasetInfo = computed(() => {
  if (!trainingForm.dataset_id) return null
  return availableDatasets.value.find(ds => ds.id === trainingForm.dataset_id)
})

const availableCustomModels = computed(() => {
  return trainingModels.value.custom_models?.filter(m =>
    m.status === 'trained' || m.status === 'published'
  ) || []
})

const filteredTrainingModels = computed(() => {
  let result = []
  if (modelFilter.value === 'all' || modelFilter.value === 'system') {
    result = [...result, ...trainingModels.value.system_models]
  }
  if (modelFilter.value === 'all' || modelFilter.value === 'custom') {
    result = [...result, ...trainingModels.value.custom_models]
  }
  return result
})

const analysisData = ref({
  total_detections: 0,
  models_used: {},
  classes_detected: {},
  avg_confidence: 0
})
const statistics = ref({
  total_patients: 0,
  total_doctors: 0,
  total_records: 0,
  today_detections: 0,
  total_detections: 0,
  avg_daily: 0,
  date_range_detections: 0
})
const dateRange = ref(null)

// 详细统计数据
const detailedStats = ref({
  gender_distribution: { male: 0, female: 0, total: 0 },
  age_distribution: {},
  department_distribution: {},
  classes_detected: {},
  models_used: {},
  daily_detections: {}
})

// 趋势分析数据
const trendPeriod = ref('week')
const trendData = ref([])
const maxTrendCount = ref(1)

// 图表相关
const classesChartRef = ref(null)
const modelsChartRef = ref(null)
const trendChartRef = ref(null)
let classesChart = null
let modelsChart = null
let trendChart = null

// 患者统计分析相关数据
const statsDateRange = ref(null)
const patientStats = ref({
  totalPatients: 0,
  totalExaminations: 0,
  positiveCases: 0,
  positiveRate: 0,
  fractureTypes: {},
  ageGroups: {},
  genderDistribution: { male: 0, female: 0 },
  monthlyTrend: []
})
const recentExaminations = ref([])

// 图表引用
const fractureTypeChartRef = ref(null)
const ageChartRef = ref(null)
const monthlyChartRef = ref(null)
const genderChartRef = ref(null)
let fractureTypeChart = null
let ageChart = null
let monthlyChart = null
let genderChart = null

// 操作日志相关数据
const logList = ref([])
const logLoading = ref(false)
const logDetailVisible = ref(false)
const currentLog = ref(null)
const logSearchForm = reactive({
  username: '',
  method: '',
  success: null,
  dateRange: null
})
const logPagination = reactive({
  page: 1,
  per_page: 20,
  total: 0
})

// 数据生成工具相关数据
const testDataConfig = reactive({
  patientCount: 20,
  examCount: 50
})
const generatingData = ref(false)
const generateResult = reactive({
  success: false,
  message: ''
})
const currentStats = reactive({
  patients: 0,
  examinations: 0,
  users: 0
})

// 年龄段颜色
const ageColors = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272']

// 年龄段分布计算属性
const ageDistribution = computed(() => {
  const ageData = detailedStats.value.age_distribution || {}
  const data = [
    { label: '0-18岁', count: ageData['0-18'] || 0 },
    { label: '19-35岁', count: ageData['19-35'] || 0 },
    { label: '36-50岁', count: ageData['36-50'] || 0 },
    { label: '51-65岁', count: ageData['51-65'] || 0 },
    { label: '65岁以上', count: ageData['65+'] || 0 }
  ]
  const total = data.reduce((sum, item) => sum + item.count, 0)
  return data.map(item => ({
    ...item,
    percentage: total > 0 ? Math.round((item.count / total) * 100) : 0
  }))
})

// 性别分布计算属性
const genderDistribution = computed(() => {
  const genderData = detailedStats.value.gender_distribution || {}
  return {
    male: genderData.male || 0,
    female: genderData.female || 0,
    total: genderData.total || 0
  }
})

// 科室分布计算属性
const departmentDistribution = computed(() => {
  const deptData = detailedStats.value.department_distribution || {}
  const data = Object.entries(deptData).map(([department, count]) => ({
    department,
    count
  }))
  const total = data.reduce((sum, item) => sum + item.count, 0)
  return data.map(item => ({
    ...item,
    percentage: total > 0 ? Math.round((item.count / total) * 100) : 0
  }))
})

const fetchAdminData = async () => {
  try {
    const res = await axios.get('/api/admin/dashboard')
    adminInfo.value = res.data.admin || {}
    pendingApprovals.value = res.data.pending_approvals || []
    processedApprovals.value = res.data.processed_approvals || []
    doctors.value = res.data.doctors || []
    patients.value = res.data.patients || []
    pendingCount.value = pendingApprovals.value.length
  } catch (err) {
    ElMessage.error('获取数据失败')
  }
}

const handleMenuSelect = (index) => {
  activeMenu.value = index
  // 切换到操作日志页面时加载数据
  if (index === 'logs') {
    loadLogs()
  }
  // 切换到系统设置页面时加载AI设置
  if (index === 'system') {
    loadAISettings()
  }
  // 切换到统计分析页面时加载患者统计数据
  if (index === 'statistics') {
    // 使用 nextTick 确保 DOM 已经渲染完成
    nextTick(() => {
      loadPatientStats()
    })
  }
  // 切换到数据生成工具页面时加载当前统计
  if (index === 'data-generator') {
    loadCurrentStats()
  }
  // 切换到公告管理页面时加载数据
  if (index === 'announcements') {
    loadAnnouncements()
  }
  // 切换到模型训练页面时加载数据
  if (index === 'training') {
    loadTrainingModels()
    loadTrainingTasks()
    loadDatasets()
  }
  // 切换到检测系统页面时加载检查记录
  if (index === 'detection') {
    fetchDetectionHistory()
  }
  // 切换到数据集管理页面时加载数据
  if (index === 'datasets') {
    loadDatasetsList()
  }
}

const handleLogout = () => {
  ElMessageBox.confirm('确定要退出登录吗？', '提示', {
    confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning'
  }).then(() => {
    localStorage.clear()
    router.push('/login')
    ElMessage.success('已退出登录')
  })
}

const viewDetail = (row) => {
  selectedDoctor.value = row
  reviewNote.value = ''
  detailVisible.value = true
}

const approveDoctor = (row) => {
  selectedDoctor.value = row
  reviewNote.value = ''
  detailVisible.value = true
}

const rejectDoctor = (row) => {
  selectedDoctor.value = row
  reviewNote.value = ''
  detailVisible.value = true
}

const confirmApprove = async () => {
  try {
    await axios.post(`/api/admin/approve-doctor/${selectedDoctor.value.id}`, {
      status: 'approved',
      note: reviewNote.value
    })
    ElMessage.success('审核通过')
    detailVisible.value = false
    fetchAdminData()
  } catch (err) {
    ElMessage.error(err.response?.data?.error || '审核失败')
  }
}

const confirmReject = async () => {
  try {
    await axios.post(`/api/admin/approve-doctor/${selectedDoctor.value.id}`, {
      status: 'rejected',
      note: reviewNote.value
    })
    ElMessage.success('已拒绝')
    detailVisible.value = false
    fetchAdminData()
  } catch (err) {
    ElMessage.error(err.response?.data?.error || '操作失败')
  }
}

const viewDoctor = (row) => {
  selectedDoctorDetail.value = row
  doctorDetailVisible.value = true
}
const disableDoctor = (row) => {
  ElMessageBox.confirm(`确定要停用医生 ${row.full_name} 吗？`, '提示', {
    confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning'
  }).then(() => {
    ElMessage.success('医生已停用')
  })
}
const viewPatient = (row) => {
  selectedPatientDetail.value = row
  patientDetailVisible.value = true
}

const editDoctor = (row) => {
  editingDoctor.value = { ...row }
  editDoctorVisible.value = true
}

const editPatient = (row) => {
  editingPatient.value = { ...row }
  editPatientVisible.value = true
}

const saveDoctorEdit = async () => {
  if (!editingDoctor.value.full_name?.trim()) {
    ElMessage.warning('请输入真实姓名')
    return
  }
  if (editingDoctor.value.phone && !/^1[3-9]\d{9}$/.test(editingDoctor.value.phone)) {
    ElMessage.warning('手机号格式不正确')
    return
  }
  
  savingDoctor.value = true
  try {
    await axios.put(`/api/admin/user/${editingDoctor.value.id}`, {
      full_name: editingDoctor.value.full_name,
      phone: editingDoctor.value.phone,
      hospital: editingDoctor.value.hospital,
      department: editingDoctor.value.department,
      title: editingDoctor.value.title,
      status: editingDoctor.value.status
    })
    ElMessage.success('医生信息更新成功')
    editDoctorVisible.value = false
    fetchAdminData() // 刷新数据
  } catch (err) {
    ElMessage.error(err.response?.data?.error || '更新失败')
  } finally {
    savingDoctor.value = false
  }
}

const savePatientEdit = async () => {
  if (!editingPatient.value.full_name?.trim()) {
    ElMessage.warning('请输入真实姓名')
    return
  }
  if (editingPatient.value.phone && !/^1[3-9]\d{9}$/.test(editingPatient.value.phone)) {
    ElMessage.warning('手机号格式不正确')
    return
  }
  
  savingPatient.value = true
  try {
    await axios.put(`/api/admin/user/${editingPatient.value.id}`, {
      full_name: editingPatient.value.full_name,
      phone: editingPatient.value.phone,
      gender: editingPatient.value.gender
    })
    ElMessage.success('患者信息更新成功')
    editPatientVisible.value = false
    fetchAdminData() // 刷新数据
  } catch (err) {
    ElMessage.error(err.response?.data?.error || '更新失败')
  } finally {
    savingPatient.value = false
  }
}

const saveConfig = () => { ElMessage.success('基础设置已保存') }

// 数据生成工具相关方法
const generateTestData = async () => {
  generatingData.value = true
  generateResult.message = ''
  
  try {
    const res = await axios.post('/api/admin/generate-test-data', {
      patient_count: testDataConfig.patientCount,
      exam_count: testDataConfig.examCount
    })
    
    if (res.data.success) {
      generateResult.success = true
      generateResult.message = res.data.message
      ElMessage.success('测试数据生成成功')
      // 刷新当前统计
      await loadCurrentStats()
    } else {
      generateResult.success = false
      generateResult.message = res.data.error || '生成失败'
      ElMessage.error(generateResult.message)
    }
  } catch (err) {
    generateResult.success = false
    generateResult.message = '生成失败: ' + (err.response?.data?.error || err.message)
    ElMessage.error(generateResult.message)
  } finally {
    generatingData.value = false
  }
}

const loadCurrentStats = async () => {
  try {
    // 获取患者数量
    const patientsRes = await axios.get('/api/patients')
    currentStats.patients = patientsRes.data?.data?.length || 0
    
    // 获取检查记录数量
    const examsRes = await axios.get('/api/examinations')
    currentStats.examinations = examsRes.data?.data?.length || 0
    
    // 获取用户数量
    const statsRes = await axios.get('/api/admin/statistics')
    currentStats.users = (statsRes.data?.total_patients || 0) + (statsRes.data?.total_doctors || 0)
  } catch (err) {
    console.error('加载统计数据失败', err)
  }
}

// AI设置相关方法
const loadAISettings = async () => {
  try {
    const res = await axios.get('/api/settings')
    Object.assign(aiSettings, res.data)
    await loadUserAIModels()
  } catch (err) {
    console.error('加载AI设置失败', err)
  }
}

const loadUserAIModels = async () => {
  try {
    const res = await axios.get('/api/user-ai-models', {
      params: { provider: aiSettings.ai_provider }
    })
    if (res.data.success) {
      userAIModels.value = res.data.data
    }
  } catch (err) {
    console.error('加载用户AI模型失败', err)
  }
}

const onUserModelSelect = (modelId) => {
  if (!modelId) return
  const selected = userAIModels.value.find(m => m.model_id === modelId)
  if (selected) {
    aiSettings.ai_api_key = selected.api_key || ''
    if (selected.api_url) {
      aiSettings.ai_api_url = selected.api_url
    }
    ElMessage.success(`已加载模型: ${modelId}`)
  }
}

const onProviderChange = async () => {
  aiSettings.ai_model = ''
  aiSettings.ai_api_key = ''
  aiSettings.ai_api_url = ''
  await loadUserAIModels()
}

const saveAISettings = async () => {
  try {
    const response = await axios.post('/api/settings', aiSettings)
    if (response.data.success) {
      ElMessage.success('AI设置已保存到数据库')
      await loadUserAIModels()
    } else {
      ElMessage.warning(response.data.message || '保存可能未成功')
    }
  } catch (err) {
    console.error('保存AI设置失败', err)
    const errorMsg = err.response?.data?.error || err.message || '未知错误'
    ElMessage.error(`保存失败：${errorMsg}`)
  }
}

const testAIConnection = async () => {
  aiTestLoading.value = true
  try {
    const testData = {
      detections: [{ class: '测试', confidence: 0.95, bbox: [0, 0, 100, 100] }],
      prompt: '这是一个连接测试，请回复"连接成功"。'
    }
    const res = await axios.post('/api/interpret', testData)
    if (res.data.success) {
      ElMessage.success(`连接成功！使用提供商: ${res.data.ai_provider || '未知'}`)
    } else {
      ElMessage.error(res.data.error || '连接失败')
    }
  } catch (err) {
    const errorMsg = err.response?.data?.error || err.message || '连接失败'
    const hint = err.response?.data?.hint || ''
    ElMessage.error(`${errorMsg}${hint ? ' - ' + hint : ''}`)
  } finally {
    aiTestLoading.value = false
  }
}

// 操作日志相关方法
const loadLogs = async () => {
  logLoading.value = true
  try {
    const params = {
      page: logPagination.page,
      per_page: logPagination.per_page
    }
    
    // 添加筛选参数
    if (logSearchForm.username) {
      params.username = logSearchForm.username
    }
    if (logSearchForm.method) {
      params.method = logSearchForm.method
    }
    if (logSearchForm.success !== null) {
      params.success = logSearchForm.success
    }
    if (logSearchForm.dateRange && logSearchForm.dateRange.length === 2) {
      params.date_from = logSearchForm.dateRange[0]
      params.date_to = logSearchForm.dateRange[1]
    }
    
    const res = await axios.get('/api/admin/logs', { params })
    logList.value = res.data.data || []
    logPagination.total = res.data.total || logList.value.length
  } catch (err) {
    ElMessage.error('加载日志失败: ' + (err.response?.data?.error || err.message))
  } finally {
    logLoading.value = false
  }
}

const handleLogSearch = () => {
  logPagination.page = 1
  loadLogs()
}

const resetLogSearch = () => {
  logSearchForm.username = ''
  logSearchForm.method = ''
  logSearchForm.success = null
  logSearchForm.dateRange = null
  logPagination.page = 1
  loadLogs()
}

const showLogDetail = (row) => {
  currentLog.value = row
  logDetailVisible.value = true
}

const handleLogSizeChange = (size) => {
  logPagination.per_page = size
  loadLogs()
}

const handleLogPageChange = (page) => {
  logPagination.page = page
  loadLogs()
}

const getMethodType = (method) => {
  const types = {
    'GET': 'info',
    'POST': 'success',
    'PUT': 'warning',
    'DELETE': 'danger'
  }
  return types[method] || 'info'
}

const formatLogTime = (timestamp) => {
  if (!timestamp) return '-'
  try {
    const date = new Date(timestamp)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    }).replace(/\//g, '-')
  } catch (e) {
    return timestamp
  }
}

// 模型训练相关方法
const publishModel = async (model) => {
  try {
    await axios.post(`/api/models/${model.id}/publish`)
    ElMessage.success('模型发布成功')
    fetchTrainedModels()
  } catch (err) {
    ElMessage.error('发布失败')
  }
}

const fetchTrainedModels = async () => {
  try {
    const res = await axios.get('/api/models')
    trainedModels.value = res.data.custom_models || []
  } catch (err) {
    console.error('获取模型列表失败', err)
  }
}

// 模型训练相关方法
const loadTrainingModels = async () => {
  modelsLoading.value = true
  try {
    const res = await axios.get('/api/models')
    trainingModels.value = {
      system_models: res.data.system_models || [],
      custom_models: res.data.custom_models || []
    }
  } catch (err) {
    ElMessage.error('加载模型列表失败')
  } finally {
    modelsLoading.value = false
  }
}

const loadTrainingTasks = async () => {
  tasksLoading.value = true
  try {
    const res = await axios.get('/api/training/tasks')
    trainingTasks.value = res.data.tasks || []
  } catch (err) {
    ElMessage.error('加载训练任务失败')
  } finally {
    tasksLoading.value = false
  }
}

const loadDatasets = async () => {
  try {
    const res = await axios.get('/api/datasets/all')
    availableDatasets.value = res.data.datasets || []
  } catch (err) {
    console.error('加载数据集列表失败:', err)
  }
}

const startTraining = async () => {
  if (!trainingForm.name) {
    ElMessage.warning('请输入模型名称')
    return
  }

  if (datasetSource.value === 'existing') {
    if (!trainingForm.dataset_id) {
      ElMessage.warning('请选择数据集')
      return
    }
  } else {
    if (!trainingForm.dataset) {
      ElMessage.warning('请上传数据集')
      return
    }
  }

  isTraining.value = true

  try {
    const formData = new FormData()
    formData.append('name', trainingForm.name)
    formData.append('description', trainingForm.description)
    formData.append('base_model', trainingForm.base_model)
    formData.append('epochs', trainingForm.epochs)
    formData.append('batch_size', trainingForm.batch_size)
    formData.append('img_size', trainingForm.img_size)
    formData.append('dataset_source', datasetSource.value)
    formData.append('use_best_hyperparams', trainingForm.use_best_hyperparams.toString())

    if (datasetSource.value === 'existing') {
      formData.append('dataset_id', trainingForm.dataset_id)
    } else {
      formData.append('dataset', trainingForm.dataset)
    }

    const res = await axios.post('/api/models/train', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })

    if (res.data.success) {
      ElMessage.success('训练任务已启动')
      resetTrainingForm()
      loadTrainingTasks()
    }
  } catch (err) {
    ElMessage.error('启动训练失败: ' + (err.response?.data?.error || err.message))
  } finally {
    isTraining.value = false
  }
}

const resetTrainingForm = () => {
  trainingForm.name = ''
  trainingForm.description = ''
  trainingForm.base_model = 'yolov8'
  trainingForm.epochs = 100
  trainingForm.batch_size = 16
  trainingForm.img_size = 640
  trainingForm.dataset = null
  trainingForm.dataset_id = null
  datasetSource.value = 'existing'
  if (uploadRef.value) {
    uploadRef.value.clearFiles()
  }
}

const onDatasetChange = (file) => {
  trainingForm.dataset = file.raw
}

const viewTaskDetail = (task) => {
  selectedTask.value = task
  taskDetailVisible.value = true
}

const viewTaskLogs = async (task) => {
  try {
    const res = await axios.get(`/api/training/tasks/${task.id}/logs`)
    trainingLogs.value = res.data.logs || '暂无日志'
    logsVisible.value = true
  } catch (err) {
    ElMessage.error('加载日志失败')
  }
}

const stopTrainingTask = async (task) => {
  try {
    await ElMessageBox.confirm(
      '确定要终止此训练任务吗？终止后无法恢复',
      '确认终止',
      {
        confirmButtonText: '确定终止',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger'
      }
    )

    await axios.post(`/api/training/tasks/${task.id}/stop`)
    ElMessage.success('训练任务已终止')
    loadTrainingTasks()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error('终止失败: ' + (err.response?.data?.error || err.message))
    }
  }
}

const viewModelDetail = (model) => {
  selectedModel.value = model
  modelDetailVisible.value = true
}

const publishTrainingModel = async (model) => {
  try {
    await ElMessageBox.confirm('确定要发布此模型吗？发布后可用于检测', '确认发布', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })

    await axios.post(`/api/models/${model.id}/publish`)
    ElMessage.success('模型已发布')
    loadTrainingModels()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error('发布失败: ' + (err.response?.data?.error || err.message))
    }
  }
}

const disableTrainingModel = async (model) => {
  try {
    await ElMessageBox.confirm('确定要禁用此模型吗？禁用后无法用于检测', '确认禁用', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })

    await axios.post(`/api/models/${model.id}/disable`)
    ElMessage.success('模型已禁用')
    loadTrainingModels()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error('禁用失败: ' + (err.response?.data?.error || err.message))
    }
  }
}

const enableTrainingModel = async (model) => {
  try {
    await ElMessageBox.confirm('确定要启用此模型吗？启用后可用于检测', '确认启用', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'primary'
    })

    await axios.post(`/api/models/${model.id}/enable`)
    ElMessage.success('模型已启用')
    loadTrainingModels()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error('启用失败: ' + (err.response?.data?.error || err.message))
    }
  }
}

const deleteTrainingModel = async (model) => {
  try {
    await ElMessageBox.confirm('确定要删除此模型吗？此操作不可恢复', '确认删除', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'danger'
    })

    await axios.delete(`/api/models/${model.id}`)
    ElMessage.success('模型已删除')
    loadTrainingModels()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error('删除失败: ' + (err.response?.data?.error || err.message))
    }
  }
}

const getTaskStatusType = (status) => {
  const map = {
    'pending': 'info',
    'running': 'primary',
    'completed': 'success',
    'failed': 'danger',
    'stopped': 'warning'
  }
  return map[status] || 'info'
}

const getTaskStatusText = (status) => {
  const map = {
    'pending': '等待中',
    'running': '训练中',
    'completed': '已完成',
    'failed': '失败',
    'stopped': '已终止'
  }
  return map[status] || status
}

const getModelStatusType = (status) => {
  const map = {
    'training': 'warning',
    'trained': 'success',
    'published': 'primary',
    'disabled': 'info'
  }
  return map[status] || 'info'
}

const getModelStatusText = (status) => {
  const map = {
    'training': '训练中',
    'trained': '已训练',
    'published': '已发布',
    'disabled': '已禁用'
  }
  return map[status] || status
}

const getMetricColor = (value) => {
  if (!value) return '#909399'
  if (value >= 0.8) return '#67c23a'
  if (value >= 0.6) return '#e6a23c'
  return '#f56c6c'
}

// 数据分析相关方法
const fetchAnalysisData = async () => {
  try {
    const res = await axios.get('/api/analysis')
    analysisData.value = res.data
  } catch (err) {
    console.error('获取分析数据失败', err)
  }
}

// 统计分析相关方法
const loadStatistics = async () => {
  try {
    const params = {}
    if (dateRange.value && dateRange.value.length === 2) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }
    // 加载基础统计数据
    const res = await axios.get('/api/admin/statistics', { params })
    statistics.value = { ...statistics.value, ...res.data }
    
    // 加载详细统计数据
    const detailedRes = await axios.get('/api/admin/statistics/detailed', { params })
    detailedStats.value = detailedRes.data
    
    // 更新图表
    updateCharts()
  } catch (err) {
    console.error('获取统计数据失败', err)
    ElMessage.error('获取统计数据失败')
  }
}

// 获取模型显示名称
const getModelDisplayName = (modelKey) => {
  if (!modelKey) return '-'
  if (modelKey === 'yolov8') return 'YOLOv8'
  if (modelKey === 'yolo11') return 'YOLO11'
  if (modelKey === 'yolo26') return 'YOLO26'
  // 自定义模型
  if (modelKey.startsWith('custom_')) {
    return modelKey.replace('custom_', '').replace(/_\d+$/, '')
  }
  return modelKey
}

// 类别颜色映射
const classColors = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272', '#fc8452', '#9a60b4']
const getClassColor = (cls) => {
  const index = Object.keys(analysisData.value.classes_detected || {}).indexOf(cls)
  return classColors[index % classColors.length]
}

// 获取总检测次数
const getTotalClassesCount = () => {
  const classes = analysisData.value.classes_detected || {}
  return Object.values(classes).reduce((sum, count) => sum + count, 0)
}

// 计算环形图数据
const classChartData = computed(() => {
  const classes = analysisData.value.classes_detected || {}
  const total = getTotalClassesCount()
  if (total === 0) return []
  
  const circumference = 2 * Math.PI * 80 // r=80
  let currentOffset = 0
  
  return Object.entries(classes).map(([cls, count], index) => {
    const percentage = count / total
    const dashArray = `${percentage * circumference} ${circumference}`
    const dashOffset = -currentOffset
    currentOffset += percentage * circumference
    
    return {
      name: cls,
      count,
      percentage: Math.round(percentage * 100),
      color: classColors[index % classColors.length],
      dashArray,
      dashOffset
    }
  })
})

// 初始化图表
const initCharts = () => {
  if (classesChartRef.value && !classesChart) {
    classesChart = echarts.init(classesChartRef.value)
  }
  if (modelsChartRef.value && !modelsChart) {
    modelsChart = echarts.init(modelsChartRef.value)
  }
  if (trendChartRef.value && !trendChart) {
    trendChart = echarts.init(trendChartRef.value)
  }
}

// 更新图表
const updateCharts = () => {
  nextTick(() => {
    initCharts()
    updateClassesChart()
    updateModelsChart()
    updateTrendChart()
  })
}

// 加载患者统计数据
const loadPatientStats = async () => {
  try {
    const params = {}
    if (statsDateRange.value && statsDateRange.value.length === 2) {
      params.start_date = statsDateRange.value[0]
      params.end_date = statsDateRange.value[1]
    }
    
    // 获取患者列表（Patient模型）
    const patientsRes = await axios.get('/api/patients', { params })
    console.log('Patients response:', patientsRes.data)
    const patients = patientsRes.data?.data || []
    
    // 获取User模型中的患者（role='patient'）- 获取所有数据
    const usersRes = await axios.get('/api/users', { params: { role: 'patient', per_page: 1000 } })
    console.log('Users response:', usersRes.data)
    const patientUsers = usersRes.data?.data || []
    const totalPatientUsers = usersRes.data?.total || patientUsers.length
    
    // 获取检查记录（测试数据）
    const examsRes = await axios.get('/api/examinations', { params })
    console.log('Examinations response:', examsRes.data)
    const examinations = examsRes.data?.data || []
    
    // 获取AI检测历史记录（真实检测数据）
    const historyRes = await axios.get('/api/history')
    console.log('Detection history response:', historyRes.data)
    const detectionHistory = historyRes.data?.data || []
    
    console.log('Patients count (Patient model):', patients.length)
    console.log('Patient users count (User model):', patientUsers.length, 'Total:', totalPatientUsers)
    console.log('Examinations count:', examinations.length)
    console.log('Detection history count:', detectionHistory.length)
    
    // 合并所有患者数据源（去重）
    const patientMap = new Map()
    
    // 添加Patient模型的患者（使用 'patient_' + id 作为key）
    patients.forEach(p => {
      patientMap.set('patient_' + p.id, p)
    })
    
    // 添加User模型中的患者（使用 'user_' + id 作为key）
    patientUsers.forEach(u => {
      patientMap.set('user_' + u.id, {
        id: u.id,
        name: u.full_name || u.username,
        age: u.patient_profile?.birth_date ? calculateAge(u.patient_profile.birth_date) : null,
        gender: u.patient_profile?.gender || null,
        source: 'user'
      })
    })
    
    // 注意：DetectionHistory中的患者应该已经包含在Patient模型或User模型中
    // 所以这里不再额外添加，避免重复统计
    
    // 合并后的患者列表
    const allPatients = Array.from(patientMap.values())
    console.log('Total unique patients:', allPatients.length)
    console.log('Patient model count:', patients.length)
    console.log('User patient count:', patientUsers.length)
    
    // 统计计算 - 患者数（去重）
    const totalPatients = allPatients.length
    
    // 检查记录数 = 测试数据 + 真实检测数据
    const totalExaminations = examinations.length + detectionHistory.length
    
    // 阳性病例统计（合并两种数据源）
    // 从examinations统计
    const examPositiveCases = examinations.filter(e => {
      const result = e.detection_result || {}
      return result.has_fracture === true
    }).length
    // 从DetectionHistory统计（count > 0表示检测到骨折）
    const historyPositiveCases = detectionHistory.filter(h => h.count > 0).length
    // 合并阳性病例
    const positiveCases = examPositiveCases + historyPositiveCases
    
    const positiveRate = totalExaminations > 0 ? ((positiveCases / totalExaminations) * 100).toFixed(1) : 0
    
    // 骨折类型统计（合并两种数据源）
    const fractureTypes = {}
    // 从examinations统计
    examinations.forEach(e => {
      const result = e.detection_result || {}
      const types = result.fracture_types || []
      types.forEach(type => {
        fractureTypes[type] = (fractureTypes[type] || 0) + 1
      })
    })
    // 从DetectionHistory统计
    detectionHistory.forEach(h => {
      const types = h.fracture_types || []
      types.forEach(type => {
        fractureTypes[type] = (fractureTypes[type] || 0) + 1
      })
    })
    
    // 年龄段统计（基于合并后的所有患者数据）
    const ageGroups = { '0-18': 0, '19-30': 0, '31-45': 0, '46-60': 0, '60+': 0 }
    allPatients.forEach(p => {
      if (p.age) {
        if (p.age <= 18) ageGroups['0-18']++
        else if (p.age <= 30) ageGroups['19-30']++
        else if (p.age <= 45) ageGroups['31-45']++
        else if (p.age <= 60) ageGroups['46-60']++
        else ageGroups['60+']++
      }
    })
    
    // 性别统计（基于合并后的所有患者数据）
    const genderDistribution = { male: 0, female: 0, unknown: 0 }
    allPatients.forEach(p => {
      if (p.gender === '男') genderDistribution.male++
      else if (p.gender === '女') genderDistribution.female++
      else genderDistribution.unknown++
    })
    
    // 月度趋势统计（合并两种数据源）
    const monthlyMap = {}
    // 从examinations统计
    examinations.forEach(e => {
      if (e.exam_date) {
        const month = e.exam_date.substring(0, 7) // YYYY-MM
        monthlyMap[month] = (monthlyMap[month] || 0) + 1
      }
    })
    // 从DetectionHistory统计
    detectionHistory.forEach(h => {
      if (h.timestamp) {
        const month = h.timestamp.substring(0, 7) // YYYY-MM
        monthlyMap[month] = (monthlyMap[month] || 0) + 1
      }
    })
    const monthlyTrend = Object.entries(monthlyMap)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([month, count]) => ({ month, count }))
    
    // 更新数据
    patientStats.value = {
      totalPatients,
      totalExaminations,
      positiveCases,
      positiveRate,
      fractureTypes,
      ageGroups,
      genderDistribution,
      monthlyTrend
    }
    
    // 最近检查记录（合并两种数据源，按时间排序）
    const examRecords = examinations.map(e => ({
      id: e.id,
      patient_name: e.patient_name || '未知',
      exam_date: e.exam_date,
      report: e.report || (e.detection_result?.has_fracture ? '检测到骨折' : '未检测到骨折'),
      created_by: e.created_by || '系统',
      source: 'examination'
    }))
    
    const historyRecords = detectionHistory.map(h => ({
      id: h.id,
      patient_name: h.patient_name || '未知',
      exam_date: h.timestamp,
      report: h.fracture_types?.join(', ') || '未检测到骨折',
      created_by: h.doctor_name || 'AI检测',
      source: 'detection'
    }))
    
    // 合并并按时间排序
    recentExaminations.value = [...examRecords, ...historyRecords]
      .sort((a, b) => new Date(b.exam_date) - new Date(a.exam_date))
      .slice(0, 10)
    
    // 更新图表
    updatePatientCharts()
  } catch (err) {
    console.error('获取患者统计数据失败', err)
    ElMessage.error('获取统计数据失败')
  }
}

// 初始化患者统计图表
const initPatientCharts = () => {
  // 如果图表已存在，先销毁
  if (fractureTypeChart) {
    fractureTypeChart.dispose()
    fractureTypeChart = null
  }
  if (ageChart) {
    ageChart.dispose()
    ageChart = null
  }
  if (monthlyChart) {
    monthlyChart.dispose()
    monthlyChart = null
  }
  if (genderChart) {
    genderChart.dispose()
    genderChart = null
  }

  // 初始化新图表
  if (fractureTypeChartRef.value) {
    fractureTypeChart = echarts.init(fractureTypeChartRef.value)
  }
  if (ageChartRef.value) {
    ageChart = echarts.init(ageChartRef.value)
  }
  if (monthlyChartRef.value) {
    monthlyChart = echarts.init(monthlyChartRef.value)
  }
  if (genderChartRef.value) {
    genderChart = echarts.init(genderChartRef.value)
  }
}

// 更新患者统计图表
const updatePatientCharts = () => {
  if (!fractureTypeChart || !ageChart || !monthlyChart || !genderChart) {
    initPatientCharts()
  }
  updateFractureTypeChart()
  updateAgeChart()
  updateMonthlyChart()
  updateGenderChart()
}

// 计算年龄
const calculateAge = (birthDate) => {
  if (!birthDate) return null
  const today = new Date()
  const birth = new Date(birthDate)
  let age = today.getFullYear() - birth.getFullYear()
  const monthDiff = today.getMonth() - birth.getMonth()
  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birth.getDate())) {
    age--
  }
  return age
}

// 骨折类型中英文映射（根据 data.yaml 中的实际类型）
const fractureTypeMap = {
  'Avlusion Fracture': '撕脱骨折',
  'Comminuted Fracture': '粉碎性骨折',
  'Compression-Crush Fracutre': '压缩性骨折',
  'Fracture Dislocation': '骨折脱位',
  'GreenStick Fracture': '青枝骨折',
  'HairLine Fracture': '发线骨折',
  'Impact Fracture': '撞击性骨折',
  'Intra-articular fracture': '关节内骨折',
  'Null': '无骨折',
  'Oblique fracture': '斜形骨折',
  'spiral fracture': '螺旋形骨折'
}

// 获取骨折类型的中文名称
const getFractureTypeName = (enName) => {
  return fractureTypeMap[enName] || enName
}

// 更新骨折类型图表
const updateFractureTypeChart = () => {
  if (!fractureTypeChart) return
  
  const data = Object.entries(patientStats.value.fractureTypes || {})
    .map(([name, value]) => ({ name: getFractureTypeName(name), value }))
    .sort((a, b) => b.value - a.value)
  
  // 如果没有数据，显示空状态
  if (data.length === 0) {
    fractureTypeChart.setOption({
      title: {
        text: '暂无数据',
        left: 'center',
        top: 'center',
        textStyle: { color: '#999', fontSize: 14 }
      },
      series: []
    }, true)
    return
  }
  
  const option = {
    title: { show: false },
    tooltip: { trigger: 'item' },
    legend: { 
      orient: 'vertical', 
      left: 'left', 
      top: 'center',
      type: 'scroll'
    },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['60%', '50%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' }},
      data: data
    }]
  }
  fractureTypeChart.setOption(option, true)
}

// 更新年龄段图表
const updateAgeChart = () => {
  if (!ageChart) return
  
  const ageData = patientStats.value.ageGroups || {}
  const categories = ['0-18', '19-30', '31-45', '46-60', '60+']
  const data = categories.map(cat => ageData[cat] || 0)
  
  // 检查是否有数据
  const hasData = data.some(v => v > 0)
  
  if (!hasData) {
    ageChart.setOption({
      title: {
        text: '暂无数据',
        left: 'center',
        top: 'center',
        textStyle: { color: '#999', fontSize: 14 }
      },
      xAxis: { type: 'category', data: categories },
      yAxis: { type: 'value' },
      series: []
    }, true)
    return
  }
  
  const option = {
    title: { show: false },
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: categories },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      data: data,
      type: 'bar',
      itemStyle: { color: '#5470c6', borderRadius: [4, 4, 0, 0] }
    }]
  }
  ageChart.setOption(option, true)
}

// 更新月度趋势图表
const updateMonthlyChart = () => {
  if (!monthlyChart) return
  
  const trend = patientStats.value.monthlyTrend || []
  
  // 如果没有数据，显示空状态
  if (trend.length === 0) {
    monthlyChart.setOption({
      title: {
        text: '暂无数据',
        left: 'center',
        top: 'center',
        textStyle: { color: '#999', fontSize: 14 }
      },
      xAxis: { type: 'category', data: [] },
      yAxis: { type: 'value' },
      series: []
    }, true)
    return
  }
  
  const option = {
    title: { show: false },
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: trend.map(t => t.month) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      data: trend.map(t => t.count),
      type: 'line',
      smooth: true,
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: 'rgba(84, 112, 198, 0.3)' }, { offset: 1, color: 'rgba(84, 112, 198, 0.05)' }]
        }
      },
      itemStyle: { color: '#5470c6' }
    }]
  }
  monthlyChart.setOption(option, true)
}

// 更新性别分布图表
const updateGenderChart = () => {
  if (!genderChart) return

  const gender = patientStats.value.genderDistribution || { male: 0, female: 0, unknown: 0 }

  // 如果没有数据，显示空状态
  if (gender.male === 0 && gender.female === 0 && gender.unknown === 0) {
    genderChart.setOption({
      title: {
        text: '暂无数据',
        left: 'center',
        top: 'center',
        textStyle: { color: '#999', fontSize: 14 }
      },
      series: []
    }, true)
    return
  }

  const data = [
    { name: '男', value: gender.male, itemStyle: { color: '#5470c6' }},
    { name: '女', value: gender.female, itemStyle: { color: '#ee6666' }}
  ]
  
  // 如果有未知性别数据，也显示出来
  if (gender.unknown > 0) {
    data.push({ name: '未知', value: gender.unknown, itemStyle: { color: '#999' } })
  }

  const option = {
    title: { 
      show: true,
      text: `总计: ${gender.male + gender.female + gender.unknown}人`,
      left: 'center',
      top: 10,
      textStyle: { fontSize: 14, color: '#666' }
    },
    tooltip: { trigger: 'item' },
    legend: { orient: 'vertical', left: 'left', top: 'center' },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['60%', '55%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' }},
      data: data
    }]
  }
  genderChart.setOption(option, true)
}

// 更新检测类别图表
const updateClassesChart = () => {
  if (!classesChart) return
  
  const classesData = detailedStats.value.classes_detected || {}
  const data = Object.entries(classesData)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 10) // 只显示前10个
  
  const option = {
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      left: 'left',
      top: 'center'
    },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['60%', '50%'],
      avoidLabelOverlap: false,
      itemStyle: {
        borderRadius: 10,
        borderColor: '#fff',
        borderWidth: 2
      },
      label: {
        show: false
      },
      emphasis: {
        label: {
          show: true,
          fontSize: 14,
          fontWeight: 'bold'
        }
      },
      data: data
    }]
  }
  
  classesChart.setOption(option)
}

// 更新模型使用图表
const updateModelsChart = () => {
  if (!modelsChart) return
  
  const modelsData = detailedStats.value.models_used || {}
  const data = Object.entries(modelsData)
    .map(([name, value]) => ({ name: getModelDisplayName(name), value }))
    .sort((a, b) => b.value - a.value)
  
  const option = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'value'
    },
    yAxis: {
      type: 'category',
      data: data.map(item => item.name)
    },
    series: [{
      type: 'bar',
      data: data.map(item => item.value),
      itemStyle: {
        color: '#5470c6',
        borderRadius: [0, 4, 4, 0]
      }
    }]
  }
  
  modelsChart.setOption(option)
}

// 更新趋势图表
const updateTrendChart = () => {
  if (!trendChart) return
  
  const dailyData = detailedStats.value.daily_detections || {}
  const sortedDates = Object.keys(dailyData).sort()
  
  // 如果数据点太多，只显示最近30天
  const displayDates = sortedDates.slice(-30)
  
  const option = {
    tooltip: {
      trigger: 'axis'
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: displayDates,
      axisLabel: {
        rotate: 45
      }
    },
    yAxis: {
      type: 'value',
      minInterval: 1
    },
    series: [{
      name: '检测次数',
      type: 'line',
      smooth: true,
      data: displayDates.map(date => dailyData[date]),
      areaStyle: {
        color: {
          type: 'linear',
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [{
            offset: 0, color: 'rgba(84, 112, 198, 0.3)'
          }, {
            offset: 1, color: 'rgba(84, 112, 198, 0.05)'
          }]
        }
      },
      itemStyle: {
        color: '#5470c6'
      }
    }]
  }
  
  trendChart.setOption(option)
}

// 趋势数据加载
const loadTrendData = async () => {
  try {
    // 模拟趋势数据，实际应该从后端获取
    const days = trendPeriod.value === 'week' ? 7 : trendPeriod.value === 'month' ? 30 : 12
    const data = []
    const today = new Date()
    
    for (let i = days - 1; i >= 0; i--) {
      const date = new Date(today)
      if (trendPeriod.value === 'year') {
        date.setMonth(date.getMonth() - i)
        data.push({
          date: `${date.getMonth() + 1}月`,
          count: Math.floor(Math.random() * 50)
        })
      } else {
        date.setDate(date.getDate() - i)
        data.push({
          date: `${date.getMonth() + 1}/${date.getDate()}`,
          count: Math.floor(Math.random() * 10)
        })
      }
    }
    
    trendData.value = data
    maxTrendCount.value = Math.max(...data.map(d => d.count), 1)
  } catch (err) {
    console.error('加载趋势数据失败', err)
  }
}

// 监听 patientStats 变化，自动更新图表
watch(patientStats, () => {
  if (activeMenu.value === 'statistics') {
    nextTick(() => {
      updatePatientCharts()
    })
  }
}, { deep: true })

// 监听 activeMenu 变化，切换到统计分析页面时初始化图表
watch(activeMenu, (newVal) => {
  if (newVal === 'statistics') {
    // 延迟初始化，确保 DOM 完全渲染
    setTimeout(() => {
      initPatientCharts()
      updatePatientCharts()
    }, 200)
  }
})

onMounted(() => {
  fetchAdminData()
  fetchTrainedModels()
  fetchAnalysisData()
  loadStatistics()
  loadTrendData()
  loadAISettings()

  // 监听窗口大小变化，调整图表
  window.addEventListener('resize', () => {
    classesChart?.resize()
    modelsChart?.resize()
    trendChart?.resize()
    fractureTypeChart?.resize()
    ageChart?.resize()
    monthlyChart?.resize()
    genderChart?.resize()
  })
})

// 公告管理方法
const loadAnnouncements = async () => {
  announcementsLoading.value = true
  try {
    const response = await axios.get('/api/admin/announcements')
    if (response.data.success) {
      announcements.value = response.data.announcements || []
    }
  } catch (error) {
    console.error('加载公告失败:', error)
    ElMessage.error('加载公告失败')
  } finally {
    announcementsLoading.value = false
  }
}

const getTargetRoleLabel = (role) => {
  const labels = { all: '全部', patient: '患者', doctor: '医生' }
  return labels[role] || role
}

const getTargetRoleType = (role) => {
  const types = { all: 'primary', patient: 'success', doctor: 'warning' }
  return types[role] || 'info'
}

const getPriorityLabel = (priority) => {
  const labels = { low: '低', normal: '普通', high: '高', urgent: '紧急' }
  return labels[priority] || priority
}

const getPriorityType = (priority) => {
  const types = { low: 'info', normal: 'success', high: 'warning', urgent: 'danger' }
  return types[priority] || 'info'
}

const viewAnnouncement = (row) => {
  viewingAnnouncement.value = row
  showViewDialog.value = true
}

const openCreateAnnouncement = () => {
  editingAnnouncement.value = null
  announcementForm.value = {
    title: '',
    content: '',
    target_role: 'all',
    priority: 'normal',
    is_active: true
  }
  showAnnouncementDialog.value = true
}

const editAnnouncement = (row) => {
  editingAnnouncement.value = row
  announcementForm.value = {
    title: row.title,
    content: row.content,
    target_role: row.target_role,
    priority: row.priority,
    is_active: row.is_active
  }
  showAnnouncementDialog.value = true
}

const deleteAnnouncement = async (row) => {
  try {
    await ElMessageBox.confirm('确定要删除这条公告吗？', '确认删除', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })

    const response = await axios.delete(`/api/admin/announcements/${row.id}`)
    if (response.data.success) {
      ElMessage.success('删除成功')
      loadAnnouncements()
    }
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除公告失败:', error)
      ElMessage.error('删除失败')
    }
  }
}

const submitAnnouncement = async () => {
  if (!announcementForm.value.title.trim()) {
    ElMessage.warning('请输入标题')
    return
  }
  if (!announcementForm.value.content.trim()) {
    ElMessage.warning('请输入内容')
    return
  }

  announcementSubmitting.value = true
  try {
    let response
    if (editingAnnouncement.value) {
      response = await axios.put(`/api/admin/announcements/${editingAnnouncement.value.id}`, announcementForm.value)
    } else {
      response = await axios.post('/api/admin/announcements', announcementForm.value)
    }

    if (response.data.success) {
      ElMessage.success(editingAnnouncement.value ? '更新成功' : '发布成功')
      showAnnouncementDialog.value = false
      resetAnnouncementForm()
      loadAnnouncements()
    }
  } catch (error) {
    console.error('提交公告失败:', error)
    ElMessage.error('操作失败')
  } finally {
    announcementSubmitting.value = false
  }
}

const resetAnnouncementForm = () => {
  editingAnnouncement.value = null
  announcementForm.value = {
    title: '',
    content: '',
    target_role: 'all',
    priority: 'normal',
    is_active: true
  }
}

// 数据集管理方法
const loadDatasetsList = async () => {
  datasetsLoading.value = true
  try {
    const res = await axios.get('/api/datasets', {
      params: {
        page: datasetPagination.page,
        per_page: datasetPagination.per_page
      }
    })
    datasetList.value = res.data.data
    datasetPagination.total = res.data.total
  } catch (err) {
    ElMessage.error('加载数据集列表失败: ' + (err.response?.data?.error || err.message))
  } finally {
    datasetsLoading.value = false
  }
}

const beforeDatasetUpload = (file) => {
  if (!file.name.endsWith('.zip')) {
    ElMessage.error('只支持zip格式的数据集文件')
    return false
  }
  return true
}

const submitDatasetUpload = () => {
  if (!datasetUploadForm.name) {
    ElMessage.warning('请输入数据集名称')
    return
  }
  datasetUploadRef.value.submit()
}

const handleDatasetUploadSuccess = (response) => {
  if (response.success) {
    ElMessage.success('数据集上传成功')
    showDatasetUploadDialog.value = false
    datasetUploadForm.name = ''
    datasetUploadForm.description = ''
    datasetUploadRef.value.clearFiles()
    loadDatasetsList()
  } else {
    ElMessage.error(response.error || '上传失败')
  }
}

const handleDatasetUploadError = (error) => {
  ElMessage.error('上传失败: ' + (error.response?.data?.error || '网络错误'))
}

const editDataset = (row) => {
  datasetEditForm.id = row.id
  datasetEditForm.name = row.name
  datasetEditForm.description = row.description || ''
  showDatasetEditDialog.value = true
}

const submitDatasetEdit = async () => {
  if (!datasetEditForm.name) {
    ElMessage.warning('请输入数据集名称')
    return
  }
  try {
    await axios.put(`/api/datasets/${datasetEditForm.id}`, {
      name: datasetEditForm.name,
      description: datasetEditForm.description
    })
    ElMessage.success('数据集信息已更新')
    showDatasetEditDialog.value = false
    loadDatasetsList()
  } catch (err) {
    ElMessage.error(err.response?.data?.error || '更新失败')
  }
}

const deleteDataset = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除数据集 "${row.name}" 吗？\n注意：此操作不可恢复！`,
      '确认删除',
      { type: 'warning' }
    )
    await axios.delete(`/api/datasets/${row.id}`)
    ElMessage.success('数据集已删除')
    loadDatasetsList()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.response?.data?.error || '删除失败')
    }
  }
}

const handleDatasetSizeChange = (size) => {
  datasetPagination.per_page = size
  loadDatasetsList()
}

const handleDatasetPageChange = (page) => {
  datasetPagination.page = page
  loadDatasetsList()
}
</script>

<style scoped>
.admin-approval { min-height: 100vh; background: #f5f7fa; }
.admin-header {
  display: flex; align-items: center; justify-content: space-between;
  background: white; border-bottom: 1px solid #e4e7ed; padding: 0 30px; height: 64px;
}
.header-left { display: flex; align-items: center; gap: 12px; }
.system-name { font-size: 20px; font-weight: 600; color: #1e293b; }
.header-right { display: flex; align-items: center; gap: 16px; }
.welcome-text { color: #64748b; }
.admin-container { height: calc(100vh - 64px); }
.admin-sidebar { background: white; border-right: 1px solid #e4e7ed; }
.admin-menu { border-right: none; padding: 20px 0; }
.menu-badge {
  margin-left: 4px;
  display: inline-flex;
  vertical-align: middle;
}
.menu-badge :deep(.el-badge__content) {
  position: relative;
  top: -6px;
  right: 0;
  transform: none;
}
.admin-main { padding: 30px; overflow-y: auto; }
.page-title { margin-bottom: 24px; color: #1e293b; font-size: 24px; font-weight: 600; }
.form-unit { margin-left: 8px; color: #64748b; }

/* 数据分析样式 */
.stat-card { text-align: center; padding: 20px; }
.stat-icon { width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; margin: 0 auto 12px; }
.stat-value { font-size: 32px; font-weight: 700; color: #1e293b; margin-bottom: 4px; }
.stat-label { font-size: 14px; color: #64748b; }

/* 环形图样式 */
.donut-chart-container { width: 200px; height: 200px; flex-shrink: 0; }
.donut-chart { width: 100%; height: 100%; }
.donut-chart circle { transition: all 0.3s ease; }

/* 检测系统模块样式 */
.detection-modules { padding: 20px; }
.module-card { cursor: pointer; transition: all 0.3s ease; text-align: center; padding: 30px 20px; }
.module-card:hover { transform: translateY(-4px); box-shadow: 0 8px 24px rgba(0,0,0,0.1); }
.module-icon { width: 80px; height: 80px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 16px; }
.detection-icon { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
.video-icon { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; }
.camera-icon { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); color: white; }
.module-title { font-size: 18px; font-weight: 600; color: #1e293b; margin-bottom: 8px; }
.module-desc { font-size: 14px; color: #64748b; }

/* 检查记录样式 */
.report-text {
  display: inline-block;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #606266;
}
.report-text:hover {
  color: #409eff;
}

/* 检测详情对话框样式 */
.detection-detail .image-card {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
}
.detection-detail .image-title {
  padding: 12px;
  background: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;
  font-weight: 500;
  text-align: center;
}
.detection-detail .image-wrapper {
  padding: 16px;
  background: #fff;
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.detection-detail .image-wrapper .el-image {
  max-width: 100%;
  max-height: 400px;
  width: auto;
  height: auto;
}

/* 医疗建议样式 */
.detection-detail .medical-advice-content {
  padding: 10px;
  font-size: 14px;
  line-height: 1.6;
  color: #303133;
}
.detection-detail .medical-advice-content h1,
.detection-detail .medical-advice-content h2,
.detection-detail .medical-advice-content h3,
.detection-detail .medical-advice-content h4 {
  margin-top: 12px;
  margin-bottom: 8px;
  font-weight: 600;
}
.detection-detail .medical-advice-content p {
  margin-bottom: 8px;
}
.detection-detail .medical-advice-content table {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
}
.detection-detail .medical-advice-content table th,
.detection-detail .medical-advice-content table td {
  border: 1px solid #dcdfe6;
  padding: 8px;
  text-align: left;
}
.detection-detail .medical-advice-content table th {
  background-color: #f5f7fa;
  font-weight: 600;
}

/* 统计分析样式 */
.stat-blue { color: #1890ff; }
.stat-green { color: #52c41a; }
.stat-purple { color: #722ed1; }
.stat-orange { color: #fa8c16; }

/* 患者统计卡片样式 */
.stats-card {
  text-align: center;
  padding: 20px;
}
.stats-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}
.stats-value {
  font-size: 32px;
  font-weight: 700;
  color: #1890ff;
  margin-bottom: 8px;
}
.stats-label {
  font-size: 14px;
  color: #64748b;
}

/* AI配置区域样式 */
.ai-config-section {
  background: #f5f7fa;
  padding: 16px;
  border-radius: 8px;
  margin-bottom: 16px;
}
</style>
