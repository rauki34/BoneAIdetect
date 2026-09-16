<template>
  <div class="doctor-workstation">
    <!-- 顶部导航 -->
    <el-header class="workstation-header">
      <div class="header-left">
        <el-icon size="28" color="#10b981"><FirstAidKit /></el-icon>
        <span class="system-name">智慧骨科云平台</span>
        <el-tag size="small" type="success">诊疗工作台</el-tag>
      </div>
      <div class="header-right">
        <span class="welcome-text">{{ doctorInfo.full_name || doctorInfo.username }}医生，您好</span>
        <el-dropdown @command="handleCommand">
          <el-avatar :size="36" :icon="UserFilled" class="user-avatar" />
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile">个人资料</el-dropdown-item>
              <el-dropdown-item command="password">修改密码</el-dropdown-item>
              <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-header>

    <el-container class="workstation-container">
      <!-- 左侧菜单 -->
      <el-aside width="220px" class="workstation-sidebar">
        <el-menu :default-active="activeMenu" class="workstation-menu" @select="handleMenuSelect">
          <el-menu-item index="dashboard">
            <el-icon><HomeFilled /></el-icon>
            <span>工作台首页</span>
          </el-menu-item>
          <el-menu-item index="patients">
            <el-icon><User /></el-icon>
            <span>患者管理</span>
          </el-menu-item>
          <el-menu-item index="records">
            <el-icon><Document /></el-icon>
            <span>病历管理</span>
          </el-menu-item>
          <el-menu-item index="detect">
            <el-icon><Camera /></el-icon>
            <span>AI辅助诊断</span>
          </el-menu-item>
          <el-menu-item index="reports">
            <el-icon><Files /></el-icon>
            <span>检查报告</span>
          </el-menu-item>
          <el-menu-item index="history">
            <el-icon><Clock /></el-icon>
            <span>检测历史</span>
          </el-menu-item>
          <el-menu-item index="knowledge" @click="router.push('/knowledge')">
            <el-icon><Collection /></el-icon>
            <span>知识库</span>
          </el-menu-item>
          <el-menu-item index="add-patient">
            <el-icon><Plus /></el-icon>
            <span>添加患者</span>
          </el-menu-item>
          <el-menu-item index="messages">
            <el-icon><ChatDotRound /></el-icon>
            <span>消息通知</span>
            <el-badge v-if="unreadMessageCount > 0" :value="unreadMessageCount" class="message-badge-menu" />
          </el-menu-item>
        </el-menu>
      </el-aside>

      <!-- 主内容区 -->
      <el-main class="workstation-main">
        <!-- 工作台首页 -->
        <div v-if="activeMenu === 'dashboard'" class="page-content">
          <h2 class="page-title">工作台首页</h2>
          <el-row :gutter="20" class="stat-cards">
            <el-col :span="6">
              <el-card class="stat-card" shadow="hover">
                <div class="stat-icon blue"><el-icon size="32"><User /></el-icon></div>
                <div class="stat-info">
                  <div class="stat-number">{{ myPatients.length }}</div>
                  <div class="stat-label">我的患者</div>
                </div>
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card class="stat-card" shadow="hover">
                <div class="stat-icon green"><el-icon size="32"><Document /></el-icon></div>
                <div class="stat-info">
                  <div class="stat-number">{{ todayRecords.length }}</div>
                  <div class="stat-label">今日病历</div>
                </div>
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card class="stat-card" shadow="hover">
                <div class="stat-icon orange"><el-icon size="32"><Camera /></el-icon></div>
                <div class="stat-info">
                  <div class="stat-number">{{ todayDetections.length }}</div>
                  <div class="stat-label">今日检测</div>
                </div>
              </el-card>
            </el-col>
            <el-col :span="6">
              <el-card class="stat-card" shadow="hover">
                <div class="stat-icon purple"><el-icon size="32"><Bell /></el-icon></div>
                <div class="stat-info">
                  <div class="stat-number">{{ pendingTasks.length }}</div>
                  <div class="stat-label">待办事项</div>
                </div>
              </el-card>
            </el-col>
          </el-row>

          <!-- 快捷操作 -->
          <el-card class="quick-actions" shadow="never">
            <template #header><span>快捷操作</span></template>
            <div class="action-buttons">
              <el-button type="primary" size="large" @click="activeMenu = 'add-patient'">
                <el-icon><Plus /></el-icon>添加新患者
              </el-button>
              <el-button type="success" size="large" @click="activeMenu = 'detect'">
                <el-icon><Camera /></el-icon>开始AI诊断
              </el-button>
              <el-button type="warning" size="large" @click="activeMenu = 'records'">
                <el-icon><Document /></el-icon>写病历
              </el-button>
            </div>
          </el-card>

          <!-- 今日待办 -->
          <el-card class="todo-list" shadow="never">
            <template #header><span>今日待办</span></template>
            <el-timeline>
              <el-timeline-item v-for="task in pendingTasks" :key="task.id" :type="task.type">
                {{ task.content }}
              </el-timeline-item>
              <el-empty v-if="pendingTasks.length === 0" description="暂无待办事项" />
            </el-timeline>
          </el-card>
        </div>

        <!-- 患者管理 -->
        <div v-if="activeMenu === 'patients'" class="page-content">
          <h2 class="page-title">患者管理</h2>
          <el-card shadow="never">
            <div class="table-header">
              <el-input v-model="patientSearch" placeholder="搜索患者姓名/病历号" style="width: 300px">
                <template #append><el-button @click="searchPatients"><el-icon><Search /></el-icon></el-button></template>
              </el-input>
              <el-button type="primary" @click="activeMenu = 'add-patient'"><el-icon><Plus /></el-icon>添加患者</el-button>
            </div>
            <el-table :data="filteredPatients" style="width: 100%">
              <el-table-column prop="patient_number" label="病历号" width="120" />
              <el-table-column prop="full_name" label="姓名" width="100" />
              <el-table-column prop="gender" label="性别" width="80" />
              <el-table-column prop="age" label="年龄" width="80" />
              <el-table-column prop="phone" label="联系电话" width="130" />
              <el-table-column prop="last_visit" label="最近就诊" width="150" />
              <el-table-column prop="status" label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ row.status === 'active' ? '在诊' : '归档' }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="250" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" @click="viewPatient(row)">查看</el-button>
                  <el-button link type="primary" @click="writeRecord(row)">写病历</el-button>
                  <el-button link type="success" @click="openMessageDialog(row)">发消息</el-button>
                  <el-button link type="danger" @click="archivePatient(row)">归档</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </div>

        <!-- 病历管理 -->
        <div v-if="activeMenu === 'records'" class="page-content">
          <h2 class="page-title">病历管理</h2>
          <el-card shadow="never">
            <div class="table-header">
              <el-input v-model="recordSearch" placeholder="搜索病历号/患者姓名" style="width: 300px">
                <template #append><el-button @click="searchRecords"><el-icon><Search /></el-icon></el-button></template>
              </el-input>
              <el-button type="primary" @click="showCreateRecord = true"><el-icon><Plus /></el-icon>新建病历</el-button>
            </div>
            <el-table :data="filteredRecords" style="width: 100%">
              <el-table-column prop="record_number" label="病历号" width="120" />
              <el-table-column prop="patient_name" label="患者姓名" width="100" />
              <el-table-column label="就诊日期" width="150">
                <template #default="{ row }">
                  {{ formatDate(row.visit_date) }}
                </template>
              </el-table-column>
              <el-table-column prop="diagnosis" label="诊断结果" show-overflow-tooltip />
              <el-table-column prop="status" label="状态" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ row.status === 'active' ? '有效' : '已归档' }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="150" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" @click="viewRecord(row)">查看</el-button>
                  <el-button link type="primary" @click="editRecord(row)">编辑</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </div>

        <!-- AI辅助诊断 -->
        <div v-if="activeMenu === 'detect'" class="page-content">
          <h2 class="page-title">AI辅助诊断</h2>
          <el-card shadow="never">
            <div class="detect-options">
              <el-radio-group v-model="detectType">
                <el-radio-button label="image">图片检测</el-radio-button>
                <el-radio-button label="video">视频流检测</el-radio-button>
                <el-radio-button label="camera">摄像头检测</el-radio-button>
              </el-radio-group>
            </div>
            <div class="detect-content">
              <p class="detect-hint">请选择检测方式，系统将自动分析骨折情况</p>
              <el-button type="primary" size="large" @click="startDetection">
                <el-icon><Camera /></el-icon>开始检测
              </el-button>
            </div>
          </el-card>
        </div>

        <!-- 检查报告 -->
        <div v-if="activeMenu === 'reports'" class="page-content">
          <h2 class="page-title">检查报告</h2>
          <el-card shadow="never">
            <el-table :data="detectionReports" style="width: 100%">
              <el-table-column prop="id" label="报告编号" width="100" />
              <el-table-column prop="patient_name" label="患者姓名" width="120" />
              <el-table-column label="骨折类型" width="150">
                <template #default="{ row }">
                  <div v-if="row.fracture_types && row.fracture_types.length > 0">
                    <el-tag v-for="(type, idx) in row.fracture_types.slice(0, 2)" :key="idx" size="small" type="danger" style="margin-right: 5px; margin-bottom: 3px;">
                      {{ type }}
                    </el-tag>
                    <span v-if="row.fracture_types.length > 2" style="color: #999; font-size: 12px;">+{{ row.fracture_types.length - 2 }}</span>
                  </div>
                  <span v-else style="color: #999;">未检测到骨折</span>
                </template>
              </el-table-column>
              <el-table-column label="检测结果" min-width="200">
                <template #default="{ row }">
                  <div v-if="row.detections && row.detections.length > 0">
                    <el-tag v-for="(det, idx) in row.detections.slice(0, 3)" :key="idx" size="small" type="success" style="margin-right: 5px; margin-bottom: 3px;">
                      {{ det.class }} ({{ (det.confidence * 100).toFixed(1) }}%)
                    </el-tag>
                    <span v-if="row.detections.length > 3" style="color: #999; font-size: 12px;">+{{ row.detections.length - 3 }} more</span>
                  </div>
                  <span v-else style="color: #999;">未检测到骨折</span>
                </template>
              </el-table-column>
              <el-table-column label="检测时间" width="180">
                <template #default="{ row }">
                  {{ formatDateTime(row.timestamp) }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="200" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" @click="viewReport(row)">查看</el-button>
                  <el-button link type="success" @click="editReport(row)">编辑</el-button>
                  <el-button link type="danger" @click="deleteReport(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="detectionReports.length === 0" description="暂无检查报告">
              <template #description>
                <div style="text-align: center;">
                  <p style="margin-bottom: 8px;">暂无检查报告</p>
                  <p style="color: #909399; font-size: 14px;">请先前往"检测历史"完成医生诊断，诊断完成后会自动生成检查报告</p>
                </div>
              </template>
            </el-empty>
          </el-card>
        </div>

        <!-- 检测历史 -->
        <div v-if="activeMenu === 'history'" class="page-content">
          <h2 class="page-title">检测历史</h2>
          <el-card shadow="never">
            <el-table :data="detectionHistory" style="width: 100%" v-loading="historyLoading" border>
              <el-table-column prop="id" label="ID" width="60" align="center" />
              <el-table-column label="检测时间" width="160" align="center">
                <template #default="{ row }">
                  {{ formatDateTime(row.timestamp) }}
                </template>
              </el-table-column>
              <el-table-column label="使用模型" width="120" align="center">
                <template #default="{ row }">
                  {{ getModelDisplayName(row.model) }}
                </template>
              </el-table-column>
              <el-table-column label="骨折类型" min-width="150">
                <template #default="{ row }">
                  <el-tag v-for="type in row.fracture_types" :key="type" size="small" type="danger" style="margin-right: 4px; margin-bottom: 2px;">
                    {{ type }}
                  </el-tag>
                  <span v-if="!row.fracture_types || row.fracture_types.length === 0" style="color: #999;">-</span>
                </template>
              </el-table-column>
              <el-table-column prop="count" label="检测数" width="80" align="center" />
              <el-table-column label="医疗建议" width="100" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.has_medical_advice ? 'success' : 'info'" size="small">
                    {{ row.has_medical_advice ? '有' : '无' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="150" fixed="right" align="center">
                <template #default="{ row }">
                  <el-button link type="primary" @click="viewHistoryDetail(row)">查看</el-button>
                  <el-button link type="danger" @click="deleteHistory(row.id)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="detectionHistory.length === 0 && !historyLoading" description="暂无检测历史" />
          </el-card>
        </div>

        <!-- 添加患者 -->
        <div v-if="activeMenu === 'add-patient'" class="page-content">
          <h2 class="page-title">添加患者</h2>
          <el-card shadow="never">
            <el-form :model="newPatient" label-width="100px" style="max-width: 600px">
              <el-form-item label="真实姓名" required>
                <el-input v-model="newPatient.full_name" placeholder="请输入患者真实姓名" />
              </el-form-item>
              <el-form-item label="身份证号" required>
                <el-input v-model="newPatient.id_card" placeholder="请输入身份证号" maxlength="18" />
              </el-form-item>
              <el-form-item label="性别" required>
                <el-radio-group v-model="newPatient.gender">
                  <el-radio label="男">男</el-radio>
                  <el-radio label="女">女</el-radio>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="出生日期" required>
                <el-date-picker v-model="newPatient.birth_date" type="date" placeholder="选择出生日期" style="width: 100%" value-format="YYYY-MM-DD" />
              </el-form-item>
              <el-form-item label="手机号码" required>
                <el-input v-model="newPatient.phone" placeholder="请输入手机号码" maxlength="11" />
              </el-form-item>
              <el-form-item label="家庭住址">
                <el-input v-model="newPatient.address" type="textarea" :rows="2" placeholder="请输入家庭住址" />
              </el-form-item>
              <el-form-item label="紧急联系人">
                <el-input v-model="newPatient.emergency_contact" placeholder="请输入紧急联系人姓名" />
              </el-form-item>
              <el-form-item label="紧急电话">
                <el-input v-model="newPatient.emergency_phone" placeholder="请输入紧急联系人电话" />
              </el-form-item>
              <el-form-item label="过敏史">
                <el-input v-model="newPatient.allergies" type="textarea" :rows="2" placeholder="请填写过敏史（没有请填'无'）" />
              </el-form-item>
              <el-form-item label="既往病史">
                <el-input v-model="newPatient.medical_history" type="textarea" :rows="3" placeholder="请填写既往病史（没有请填'无'）" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="saving" @click="savePatient">保存</el-button>
                <el-button @click="resetPatientForm">重置</el-button>
                <el-button type="warning" @click="autoFillPatient">一键生成</el-button>
              </el-form-item>
            </el-form>
          </el-card>
        </div>

        <!-- 消息通知 -->
        <div v-if="activeMenu === 'messages'" class="page-content">
          <h2 class="page-title">消息通知</h2>

          <!-- 系统公告 -->
          <el-card shadow="never" style="margin-bottom: 20px;">
            <template #header>
              <div style="display: flex; align-items: center; justify-content: space-between;">
                <span style="font-weight: 600;">
                  <el-icon style="margin-right: 8px;"><Bell /></el-icon>系统公告
                </span>
                <el-badge v-if="unreadAnnouncementCount > 0" :value="unreadAnnouncementCount" type="danger" />
              </div>
            </template>
            <div v-if="announcements.length === 0" style="text-align: center; padding: 40px; color: #909399;">
              <el-icon :size="48" color="#dcdfe6"><Bell /></el-icon>
              <p style="margin-top: 10px;">暂无系统公告</p>
            </div>
            <div v-else>
              <div
                v-for="announcement in announcements"
                :key="announcement.id"
                class="announcement-item"
                style="padding: 15px; border-bottom: 1px solid #ebeef5; cursor: pointer; transition: background 0.2s;"
                :style="announcement.is_read ? {} : { background: '#f0f9ff' }"
                @click="viewAnnouncement(announcement)"
              >
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                  <el-tag v-if="!announcement.is_read" type="danger" size="small">未读</el-tag>
                  <el-tag :type="getAnnouncementPriorityType(announcement.priority)" size="small">
                    {{ getAnnouncementPriorityLabel(announcement.priority) }}
                  </el-tag>
                  <span style="font-weight: 600; flex: 1;">{{ announcement.title }}</span>
                  <span style="color: #c0c4cc; font-size: 12px;">{{ formatDateTime(announcement.created_at) }}</span>
                </div>
                <div style="color: #606266; font-size: 14px; line-height: 1.5; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;">
                  {{ announcement.content }}
                </div>
              </div>
            </div>
          </el-card>

          <!-- 患者消息 -->
          <el-card shadow="never" v-loading="contactsLoading">
            <template #header>
              <span style="font-weight: 600;">
                <el-icon style="margin-right: 8px;"><ChatDotRound /></el-icon>患者消息
              </span>
            </template>
            <div v-if="messageContacts.length === 0" class="empty-messages" style="text-align: center; padding: 60px 20px;">
              <el-icon :size="64" color="#dcdfe6"><ChatDotRound /></el-icon>
              <p style="color: #909399; margin-top: 20px;">暂无消息</p>
              <p style="color: #c0c4cc; font-size: 14px;">当患者给您发送消息时，会显示在这里</p>
            </div>
            <div v-else class="message-contacts-list">
              <div
                v-for="contact in messageContacts"
                :key="contact.id"
                class="contact-item"
                style="display: flex; align-items: center; padding: 15px; border-bottom: 1px solid #ebeef5; cursor: pointer; transition: background 0.2s;"
                :style="contact.unread_count > 0 ? { background: '#f0f9ff' } : {}"
                @click="openMessageDialog(contact)"
              >
                <el-avatar :size="50" :icon="UserFilled" style="margin-right: 15px;" />
                <div class="contact-info" style="flex: 1;">
                  <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 5px;">
                    <span style="font-weight: 600; font-size: 16px;">{{ contact.full_name }}</span>
                    <el-tag v-if="contact.is_primary" type="success" size="small">主治患者</el-tag>
                    <el-badge v-if="contact.unread_count > 0" :value="contact.unread_count" type="danger" />
                  </div>
                  <div style="color: #909399; font-size: 14px;">
                    <span v-if="contact.last_message">{{ contact.last_message }}</span>
                    <span v-else>暂无消息</span>
                  </div>
                  <div v-if="contact.last_message_time" style="color: #c0c4cc; font-size: 12px; margin-top: 4px;">
                    {{ formatDateTime(contact.last_message_time) }}
                  </div>
                </div>
                <el-button type="primary" link>
                  <el-icon><ChatDotRound /></el-icon>
                  聊天
                </el-button>
              </div>
            </div>
          </el-card>
        </div>
      </el-main>
    </el-container>

    <!-- 新建病历弹窗 -->
    <el-dialog v-model="showCreateRecord" title="新建病历" width="700px">
      <el-form :model="newRecord" label-width="100px">
        <el-form-item label="选择患者" required>
          <el-select v-model="newRecord.patient_id" placeholder="请选择患者" style="width: 100%" filterable>
            <el-option v-for="p in allPatients" :key="p.id" :label="`${p.full_name} (${p.patient_number})`" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="症状描述" required>
          <el-input v-model="newRecord.symptoms" type="textarea" :rows="3" placeholder="请详细描述患者症状" />
        </el-form-item>
        <el-form-item label="诊断结果" required>
          <el-input v-model="newRecord.diagnosis" type="textarea" :rows="3" placeholder="请输入诊断结果" />
        </el-form-item>
        <el-form-item label="治疗方案" required>
          <el-input v-model="newRecord.treatment" type="textarea" :rows="3" placeholder="请输入治疗方案" />
        </el-form-item>
        <el-form-item label="医嘱">
          <el-input v-model="newRecord.advice" type="textarea" :rows="2" placeholder="请输入医嘱" />
        </el-form-item>
        <el-form-item label="复诊日期">
          <el-date-picker v-model="newRecord.follow_up_date" type="date" placeholder="选择复诊日期" style="width: 100%" value-format="YYYY-MM-DD" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateRecord = false">取消</el-button>
        <el-button type="warning" @click="autoFillRecord">一键生成</el-button>
        <el-button type="primary" :loading="savingRecord" @click="saveRecord">保存病历</el-button>
      </template>
    </el-dialog>

    <!-- 编辑病历弹窗 -->
    <el-dialog v-model="showEditRecord" title="编辑病历" width="700px">
      <el-form :model="editRecordForm" label-width="100px">
        <el-form-item label="患者姓名">
          <el-input v-model="editRecordForm.patient_name" disabled />
        </el-form-item>
        <el-form-item label="症状描述" required>
          <el-input v-model="editRecordForm.symptoms" type="textarea" :rows="3" placeholder="请详细描述患者症状" />
        </el-form-item>
        <el-form-item label="诊断结果" required>
          <el-input v-model="editRecordForm.diagnosis" type="textarea" :rows="3" placeholder="请输入诊断结果" />
        </el-form-item>
        <el-form-item label="治疗方案" required>
          <el-input v-model="editRecordForm.treatment" type="textarea" :rows="3" placeholder="请输入治疗方案" />
        </el-form-item>
        <el-form-item label="医嘱">
          <el-input v-model="editRecordForm.advice" type="textarea" :rows="2" placeholder="请输入医嘱" />
        </el-form-item>
        <el-form-item label="复诊日期">
          <el-date-picker v-model="editRecordForm.follow_up_date" type="date" placeholder="选择复诊日期" style="width: 100%" value-format="YYYY-MM-DD" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditRecord = false">取消</el-button>
        <el-button type="primary" :loading="savingEditRecord" @click="saveEditRecord">保存修改</el-button>
      </template>
    </el-dialog>

    <!-- 个人资料弹窗 -->
    <el-dialog v-model="showProfileDialog" title="个人资料" width="700px">
      <el-descriptions :column="2" border>
        <el-descriptions-item label="用户名">{{ doctorInfo.username || '-' }}</el-descriptions-item>
        <el-descriptions-item label="真实姓名">{{ doctorInfo.full_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="所属医院">{{ doctorInfo.hospital || '-' }}</el-descriptions-item>
        <el-descriptions-item label="科室">{{ doctorInfo.department || '-' }}</el-descriptions-item>
        <el-descriptions-item label="职称">{{ doctorInfo.title || '-' }}</el-descriptions-item>
        <el-descriptions-item label="执业证号">{{ doctorInfo.license_number || '-' }}</el-descriptions-item>
        <el-descriptions-item label="联系电话">{{ doctorInfo.phone || '-' }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ doctorInfo.email || '-' }}</el-descriptions-item>
        <el-descriptions-item label="专业特长" :span="2">{{ doctorInfo.specialty || '-' }}</el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="showProfileDialog = false">关闭</el-button>
        <el-button type="primary" @click="openEditProfile">编辑资料</el-button>
      </template>
    </el-dialog>

    <!-- 编辑个人资料弹窗 -->
    <el-dialog v-model="showEditProfileDialog" title="编辑个人资料" width="600px">
      <el-form :model="editProfileForm" label-width="100px">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="真实姓名">
              <el-input v-model="editProfileForm.full_name" placeholder="请输入真实姓名" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="联系电话">
              <el-input v-model="editProfileForm.phone" placeholder="请输入手机号" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="所属医院">
              <el-input v-model="editProfileForm.hospital" placeholder="请输入医院名称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="科室">
              <el-input v-model="editProfileForm.department" placeholder="请输入科室" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="职称">
              <el-select v-model="editProfileForm.title" placeholder="请选择职称" style="width: 100%">
                <el-option label="住院医师" value="住院医师" />
                <el-option label="主治医师" value="主治医师" />
                <el-option label="副主任医师" value="副主任医师" />
                <el-option label="主任医师" value="主任医师" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="执业证号">
              <el-input v-model="editProfileForm.license_number" placeholder="请输入执业证号" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="邮箱">
          <el-input v-model="editProfileForm.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="专业特长">
          <el-input v-model="editProfileForm.specialty" type="textarea" :rows="3" placeholder="请输入专业特长" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditProfileDialog = false">取消</el-button>
        <el-button type="warning" @click="autoFillProfile">一键生成</el-button>
        <el-button type="primary" :loading="savingProfile" @click="saveProfile">保存</el-button>
      </template>
    </el-dialog>

    <!-- 修改密码弹窗 -->
    <el-dialog v-model="showPasswordDialog" title="修改密码" width="400px">
      <el-form :model="passwordForm" label-width="100px">
        <el-form-item label="原密码">
          <el-input v-model="passwordForm.oldPassword" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="passwordForm.newPassword" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认密码">
          <el-input v-model="passwordForm.confirmPassword" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPasswordDialog = false">取消</el-button>
        <el-button type="primary" @click="changePassword">确定</el-button>
      </template>
    </el-dialog>

    <!-- 查看患者详情弹窗 -->
    <el-dialog v-model="patientDetailVisible" title="患者详情" width="700px">
      <el-descriptions :column="2" border v-if="selectedPatient">
        <el-descriptions-item label="患者姓名">{{ selectedPatient.full_name }}</el-descriptions-item>
        <el-descriptions-item label="病历号">{{ selectedPatient.patient_number }}</el-descriptions-item>
        <el-descriptions-item label="性别">{{ selectedPatient.gender }}</el-descriptions-item>
        <el-descriptions-item label="年龄">{{ selectedPatient.age }}岁</el-descriptions-item>
        <el-descriptions-item label="联系电话">{{ selectedPatient.phone }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="selectedPatient.status === 'active' ? 'success' : 'info'">
            {{ selectedPatient.status === 'active' ? '正常' : '已归档' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="patientDetailVisible = false">关闭</el-button>
        <el-button type="primary" @click="writeRecordFromDetail">写病历</el-button>
      </template>
    </el-dialog>

    <!-- 查看病历详情弹窗 -->
    <el-dialog v-model="recordDetailVisible" title="病历详情" width="800px">
      <el-descriptions :column="1" border v-if="selectedRecord">
        <el-descriptions-item label="病历号">{{ selectedRecord.record_number }}</el-descriptions-item>
        <el-descriptions-item label="患者姓名">{{ selectedRecord.patient_name }}</el-descriptions-item>
        <el-descriptions-item label="就诊日期">{{ formatDate(selectedRecord.visit_date) }}</el-descriptions-item>
        <el-descriptions-item label="症状描述">{{ selectedRecord.symptoms }}</el-descriptions-item>
        <el-descriptions-item label="诊断结果">{{ selectedRecord.diagnosis }}</el-descriptions-item>
        <el-descriptions-item label="治疗方案">{{ selectedRecord.treatment }}</el-descriptions-item>
        <el-descriptions-item label="医嘱">{{ selectedRecord.advice || '无' }}</el-descriptions-item>
        <el-descriptions-item label="复诊日期">{{ selectedRecord.follow_up_date ? formatDate(selectedRecord.follow_up_date) : '无' }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="selectedRecord.status === 'active' ? 'success' : 'info'">
            {{ selectedRecord.status === 'active' ? '有效' : '已归档' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="recordDetailVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 查看检查报告详情弹窗 - 显示AI建议+医生诊断 -->
    <el-dialog v-model="reportDetailVisible" title="检查报告详情" width="800px" :close-on-click-modal="false">
      <div v-if="selectedReport" class="report-detail">
        <!-- 基本信息 -->
        <el-descriptions :column="3" border style="margin-bottom: 20px;">
          <el-descriptions-item label="报告编号">{{ selectedReport.id }}</el-descriptions-item>
          <el-descriptions-item label="患者姓名">{{ selectedReport.patient_name || '未知' }}</el-descriptions-item>
          <el-descriptions-item label="检测时间">{{ formatDateTime(selectedReport.timestamp) }}</el-descriptions-item>
          <el-descriptions-item label="使用模型">{{ getModelDisplayName(selectedReport.model) }}</el-descriptions-item>
          <el-descriptions-item label="检测数量">{{ selectedReport.count || 0 }} 个</el-descriptions-item>
          <el-descriptions-item label="平均置信度">
            <span v-if="selectedReport.confidence">{{ (selectedReport.confidence * 100).toFixed(1) }}%</span>
            <span v-else>-</span>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 图片对比 -->
        <h4 style="margin-bottom: 12px;">图片对比</h4>
        <el-row :gutter="20" style="margin-bottom: 20px;">
          <el-col :span="12">
            <div class="detail-image-card">
              <div class="detail-image-title">原始图片</div>
              <div class="detail-image-wrapper">
                <el-image
                  v-if="selectedReport.original_image"
                  :src="selectedReport.original_image"
                  fit="contain"
                  :preview-src-list="[selectedReport.original_image, selectedReport.result_image]"
                />
                <el-empty v-else description="原图未保存" />
              </div>
            </div>
          </el-col>
          <el-col :span="12">
            <div class="detail-image-card">
              <div class="detail-image-title">检测结果</div>
              <div class="detail-image-wrapper">
                <el-image
                  v-if="selectedReport.result_image"
                  :src="selectedReport.result_image"
                  fit="contain"
                  :preview-src-list="[selectedReport.result_image, selectedReport.original_image]"
                />
                <el-empty v-else description="结果图未保存" />
              </div>
            </div>
          </el-col>
        </el-row>

        <!-- 检测详情 -->
        <h4 style="margin-bottom: 12px;">检测详情</h4>
        <el-table :data="selectedReport.detections" border size="small" style="margin-bottom: 20px;" v-if="selectedReport.detections && selectedReport.detections.length > 0">
          <el-table-column type="index" label="序号" width="60" align="center" />
          <el-table-column prop="class" label="类别" width="120" />
          <el-table-column label="置信度" width="150">
            <template #default="{ row }">
              <el-progress
                :percentage="Math.round(row.confidence * 100)"
                :color="getConfidenceColor(row.confidence)"
                :stroke-width="12"
              />
            </template>
          </el-table-column>
          <el-table-column prop="bbox" label="检测框坐标" />
        </el-table>
        <el-empty v-else description="暂无检测详情" style="margin: 20px 0;" />

        <!-- AI医疗建议 -->
        <div v-if="selectedReport.has_medical_advice && selectedReport.medical_advice">
          <h4 style="margin-bottom: 12px;">
            <el-icon style="margin-right: 5px; color: #409EFF;"><MagicStick /></el-icon>
            AI 辅助诊断建议
          </h4>
          <el-alert
            title="AI 辅助诊断建议仅供参考，具体诊断请咨询专业医生"
            type="info"
            :closable="false"
            style="margin-bottom: 12px;"
          />
          <el-card shadow="never" style="margin-bottom: 20px; background-color: #f5f7fa;">
            <div v-if="typeof selectedReport.medical_advice === 'object'">
              <!-- 显示interpretation（原系统保存的格式） -->
              <div v-if="selectedReport.medical_advice.interpretation" class="markdown-body">
                <vue-markdown :source="selectedReport.medical_advice.interpretation" />
              </div>
              <CitationList
                v-if="selectedReport.medical_advice.references?.length"
                :references="selectedReport.medical_advice.references"
              />
              <!-- 显示结构化字段 -->
              <p v-if="selectedReport.medical_advice.diagnosis"><strong>AI诊断：</strong>{{ selectedReport.medical_advice.diagnosis }}</p>
              <p v-if="selectedReport.medical_advice.treatment"><strong>治疗建议：</strong>{{ selectedReport.medical_advice.treatment }}</p>
              <p v-if="selectedReport.medical_advice.precautions"><strong>注意事项：</strong>{{ selectedReport.medical_advice.precautions }}</p>
            </div>
            <p v-else>{{ selectedReport.medical_advice }}</p>
          </el-card>
        </div>
        <el-empty v-else description="暂无AI建议" style="margin: 20px 0;" />

        <!-- 医生诊断结论 -->
        <div v-if="selectedReport.diagnosis || selectedReport.follow_up_notes">
          <h4 style="margin-bottom: 12px;">
            <el-icon style="margin-right: 5px; color: #67c23a;"><FirstAidKit /></el-icon>
            医生诊断
          </h4>
          <el-card shadow="never" style="background-color: #f0f9ff;">
            <p v-if="selectedReport.diagnosis"><strong>诊断结论：</strong>{{ selectedReport.diagnosis }}</p>
            <p v-if="selectedReport.follow_up_notes"><strong>随访备注：</strong>{{ selectedReport.follow_up_notes }}</p>
          </el-card>
        </div>
      </div>
      <template #footer>
        <el-button @click="reportDetailVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 查看检测历史详情弹窗 - 只显示AI生成的检测结果 -->
    <el-dialog v-model="historyDetailVisible" title="检测历史详情" width="800px" :close-on-click-modal="false">
      <div v-if="selectedHistory" class="history-detail">
        <!-- 基本信息 -->
        <el-descriptions :column="3" border style="margin-bottom: 20px;">
          <el-descriptions-item label="检测ID">{{ selectedHistory.id }}</el-descriptions-item>
          <el-descriptions-item label="检测时间">{{ formatDateTime(selectedHistory.timestamp) }}</el-descriptions-item>
          <el-descriptions-item label="使用模型">{{ getModelDisplayName(selectedHistory.model) }}</el-descriptions-item>
          <el-descriptions-item label="检测数量">{{ selectedHistory.count || 0 }} 个</el-descriptions-item>
          <el-descriptions-item label="平均置信度">
            <span v-if="selectedHistory.confidence">{{ (selectedHistory.confidence * 100).toFixed(1) }}%</span>
            <span v-else>-</span>
          </el-descriptions-item>
        </el-descriptions>

        <!-- 图片对比 -->
        <h4 style="margin-bottom: 12px;">图片对比</h4>
        <el-row :gutter="20" style="margin-bottom: 20px;">
          <el-col :span="12">
            <div class="detail-image-card">
              <div class="detail-image-title">原始图片</div>
              <div class="detail-image-wrapper">
                <el-image
                  v-if="selectedHistory.original_image"
                  :src="selectedHistory.original_image"
                  fit="contain"
                  :preview-src-list="[selectedHistory.original_image, selectedHistory.result_image]"
                />
                <el-empty v-else description="原图未保存" />
              </div>
            </div>
          </el-col>
          <el-col :span="12">
            <div class="detail-image-card">
              <div class="detail-image-title">检测结果</div>
              <div class="detail-image-wrapper">
                <el-image
                  v-if="selectedHistory.result_image"
                  :src="selectedHistory.result_image"
                  fit="contain"
                  :preview-src-list="[selectedHistory.result_image, selectedHistory.original_image]"
                />
                <el-empty v-else description="结果图未保存" />
              </div>
            </div>
          </el-col>
        </el-row>

        <!-- 检测详情 -->
        <h4 style="margin-bottom: 12px;">检测详情</h4>
        <el-table :data="selectedHistory.detections" border size="small" style="margin-bottom: 20px;" v-if="selectedHistory.detections && selectedHistory.detections.length > 0">
          <el-table-column type="index" label="序号" width="60" align="center" />
          <el-table-column prop="class" label="类别" width="120" />
          <el-table-column label="置信度" width="150">
            <template #default="{ row }">
              <el-progress
                :percentage="Math.round(row.confidence * 100)"
                :color="getConfidenceColor(row.confidence)"
                :stroke-width="12"
              />
            </template>
          </el-table-column>
          <el-table-column prop="bbox" label="检测框坐标" />
        </el-table>
        <el-empty v-else description="暂无检测详情" style="margin: 20px 0;" />

        <!-- AI医疗建议 -->
        <div v-if="selectedHistory.has_medical_advice && selectedHistory.medical_advice">
          <h4 style="margin-bottom: 12px;">
            <el-icon style="margin-right: 5px; color: #409EFF;"><MagicStick /></el-icon>
            AI 辅助诊断建议
          </h4>
          <el-alert
            title="AI 辅助诊断建议仅供参考，具体诊断请咨询专业医生"
            type="info"
            :closable="false"
            style="margin-bottom: 12px;"
          />
          <el-card shadow="never" style="margin-bottom: 20px; background-color: #f5f7fa;">
            <div v-if="typeof selectedHistory.medical_advice === 'object'">
              <div v-if="selectedHistory.medical_advice.interpretation" class="markdown-body">
                <vue-markdown :source="selectedHistory.medical_advice.interpretation" />
              </div>
              <CitationList
                v-if="selectedHistory.medical_advice.references?.length"
                :references="selectedHistory.medical_advice.references"
              />
            </div>
            <p v-else>{{ selectedHistory.medical_advice }}</p>
          </el-card>
        </div>
        <el-empty v-else description="暂无AI建议" style="margin: 20px 0;" />
      </div>
      <template #footer>
        <el-button @click="historyDetailVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 编辑医生诊断弹窗 -->
    <el-dialog v-model="editReportVisible" title="编辑医生诊断" width="700px">
      <el-form :model="editReportForm" label-width="100px" v-if="editReportForm">
        <el-form-item label="报告编号">
          <el-input v-model="editReportForm.id" disabled />
        </el-form-item>
        <el-form-item label="患者姓名">
          <el-input v-model="editReportForm.patient_name" disabled />
        </el-form-item>
        <el-form-item label="诊断结论">
          <el-input v-model="editReportForm.diagnosis" type="textarea" :rows="4" placeholder="请输入医生诊断结论" />
        </el-form-item>
        <el-form-item label="随访备注">
          <el-input v-model="editReportForm.follow_up_notes" type="textarea" :rows="3" placeholder="请输入随访备注" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editReportVisible = false">取消</el-button>
        <el-button type="warning" @click="autoFillReport">一键生成</el-button>
        <el-button type="primary" @click="saveReportEdit" :loading="savingReport">保存</el-button>
      </template>
    </el-dialog>

    <!-- 消息对话框 -->
    <el-dialog
      v-model="messageDialogVisible"
      :title="messagePatient ? `与 ${messagePatient.full_name} 患者对话` : '发送消息'"
      width="600px"
      :close-on-click-modal="false"
    >
      <!-- 聊天记录区域 -->
      <div
        v-loading="chatLoading"
        class="chat-messages"
        style="max-height: 400px; overflow-y: auto; padding: 15px; background: #f5f5f5; border-radius: 8px; margin-bottom: 15px;"
      >
        <div v-if="chatMessages.length === 0" class="empty-chat" style="text-align: center; color: #999; padding: 40px;">
          <el-icon :size="48" style="margin-bottom: 10px;"><ChatDotRound /></el-icon>
          <p>暂无聊天记录，发送第一条消息开始对话吧</p>
        </div>
        <div
          v-for="msg in chatMessages"
          :key="msg.id"
          :class="['message-item', msg.sender_id === doctorInfo?.id ? 'message-sent' : 'message-received']"
          style="margin-bottom: 15px; display: flex; flex-direction: column;"
        >
          <!-- 发送者名称 -->
          <span
            :style="[
              msg.sender_id === doctorInfo?.id ? { alignSelf: 'flex-end' } : { alignSelf: 'flex-start' },
              { fontSize: '12px', color: '#666', marginBottom: '4px', fontWeight: 500 }
            ]"
          >
            {{ msg.sender_id === doctorInfo?.id ? '我' : (messagePatient?.full_name || '患者') }}
          </span>
          <div
            :style="[
              msg.sender_id === doctorInfo?.id
                ? { alignSelf: 'flex-end', background: '#3b82f6', color: 'white', borderRadius: '12px 12px 2px 12px' }
                : { alignSelf: 'flex-start', background: 'white', color: '#333', borderRadius: '12px 12px 12px 2px' },
              { maxWidth: '70%', padding: '10px 15px', boxShadow: '0 1px 2px rgba(0,0,0,0.1)' }
            ]"
          >
            <p style="margin: 0; line-height: 1.5;">{{ msg.content }}</p>
          </div>
          <span
            :style="[
              msg.sender_id === doctorInfo?.id ? { alignSelf: 'flex-end' } : { alignSelf: 'flex-start' },
              { fontSize: '12px', color: '#999', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }
            ]"
          >
            {{ formatDateTime(msg.created_at) }}
            <!-- 已读状态提示 -->
            <template v-if="msg.sender_id === doctorInfo?.id">
              <el-icon v-if="msg.is_read" style="color: #10b981; font-size: 14px;"><Check /></el-icon>
              <span v-else style="color: #999; font-size: 11px;">未读</span>
            </template>
          </span>
        </div>
      </div>

      <!-- 发送消息区域 -->
      <div class="message-input-area" style="display: flex; gap: 10px;">
        <el-input
          v-model="messageContent"
          type="textarea"
          :rows="3"
          placeholder="请输入您想对患者说的话..."
          maxlength="500"
          show-word-limit
          @keyup.enter.ctrl="sendMessage"
        />
        <el-button
          type="primary"
          :loading="messageLoading"
          @click="sendMessage"
          style="height: auto;"
        >
          <el-icon><Position /></el-icon>
          发送
        </el-button>
      </div>
      <template #footer>
        <el-button @click="messageDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 公告详情弹窗 -->
    <el-dialog
      v-model="announcementDialogVisible"
      title="公告详情"
      width="600px"
    >
      <div v-if="viewingAnnouncement">
        <h3 style="margin-bottom: 16px; font-size: 18px;">{{ viewingAnnouncement.title }}</h3>
        <div style="margin-bottom: 16px;">
          <el-tag :type="getAnnouncementPriorityType(viewingAnnouncement.priority)" style="margin-right: 8px;">
            {{ getAnnouncementPriorityLabel(viewingAnnouncement.priority) }}
          </el-tag>
          <span style="color: #909399; font-size: 14px;">
            发布时间：{{ formatDateTime(viewingAnnouncement.created_at) }}
          </span>
        </div>
        <div style="line-height: 1.8; white-space: pre-wrap; color: #303133; font-size: 15px; padding: 16px; background: #f5f7fa; border-radius: 8px;">
          {{ viewingAnnouncement.content }}
        </div>
      </div>
    </el-dialog>


  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { User, UserFilled, FirstAidKit, HomeFilled, Document, Camera, Files, Plus, Search, Bell, View, Edit, Delete, MagicStick, Clock, ChatDotRound, Position, Check, Collection } from '@element-plus/icons-vue'
import VueMarkdown from 'vue-markdown-render'
import 'github-markdown-css/github-markdown-light.css'
import axios from '../utils/axios'
import CitationList from '../components/CitationList.vue'
import { formatDate, formatDateTime } from '../utils/datetime'
import { clearAuth } from '../utils/auth'

const router = useRouter()

const activeMenu = ref('dashboard')
const doctorInfo = ref({})
const myPatients = ref([])
const allPatients = ref([])  // 所有患者列表（用于创建病历选择）
const medicalRecords = ref([])
const todayRecords = ref([])
const todayDetections = ref([])
const pendingTasks = ref([])
const detectionReports = ref([])
const detectionHistory = ref([])
const historyLoading = ref(false)
const patientSearch = ref('')
const recordSearch = ref('')
const detectType = ref('image')
const showCreateRecord = ref(false)
const saving = ref(false)
const savingRecord = ref(false)
const showProfileDialog = ref(false)
const showEditProfileDialog = ref(false)
const showPasswordDialog = ref(false)
const patientDetailVisible = ref(false)
const recordDetailVisible = ref(false)
const reportDetailVisible = ref(false)
const historyDetailVisible = ref(false)
const selectedPatient = ref(null)
const selectedRecord = ref(null)
const selectedReport = ref(null)
const selectedHistory = ref(null)

// 编辑报告相关
const editReportVisible = ref(false)
const editReportForm = ref(null)
const savingReport = ref(false)

// 编辑病历相关
const showEditRecord = ref(false)
const editRecordForm = reactive({
  id: '',
  patient_id: '',
  patient_name: '',
  symptoms: '',
  diagnosis: '',
  treatment: '',
  advice: '',
  follow_up_date: ''
})
const savingEditRecord = ref(false)

const passwordForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
})
const editProfileForm = reactive({
  full_name: '',
  phone: '',
  email: '',
  hospital: '',
  department: '',
  title: '',
  license_number: '',
  specialty: ''
})
const savingProfile = ref(false)

const newPatient = reactive({
  full_name: '', id_card: '', gender: '男', birth_date: '', phone: '',
  address: '', emergency_contact: '', emergency_phone: '', allergies: '', medical_history: ''
})

const newRecord = reactive({
  patient_id: '', symptoms: '', diagnosis: '', treatment: '', advice: '', follow_up_date: ''
})

// 消息功能相关
const messageDialogVisible = ref(false)
const messagePatient = ref(null)
const messageContent = ref('')
const messageLoading = ref(false)
const chatMessages = ref([])
const chatLoading = ref(false)
const messageContacts = ref([])
const contactsLoading = ref(false)
const unreadMessageCount = ref(0)

// 公告相关
const announcements = ref([])
const unreadAnnouncementCount = ref(0)
const announcementDialogVisible = ref(false)
const viewingAnnouncement = ref(null)

// 打开消息对话框
const openMessageDialog = (patient) => {
  messagePatient.value = patient
  messageContent.value = ''
  messageDialogVisible.value = true
  // 加载聊天记录
  loadChatHistory(patient.id)
}

// 加载聊天记录
const loadChatHistory = async (patientId) => {
  chatLoading.value = true
  try {
    const response = await axios.get(`/api/messages/conversation/${patientId}`)
    if (response.data.success) {
      chatMessages.value = response.data.messages || []
      // 检查是否有来自患者的未读消息
      const hasUnreadFromPatient = chatMessages.value.some(
        msg => msg.sender_id === patientId && !msg.is_read
      )
      // 只有在有未读消息时才标记为已读
      if (hasUnreadFromPatient) {
        await axios.post('/api/messages/mark-read', { sender_id: patientId })
        // 刷新未读消息数
        await fetchMessageContacts()
      }
    }
  } catch (error) {
    console.error('加载聊天记录失败:', error)
  } finally {
    chatLoading.value = false
  }
}

// 发送消息
const sendMessage = async () => {
  if (!messageContent.value.trim()) {
    ElMessage.warning('请输入消息内容')
    return
  }
  if (!messagePatient.value) {
    ElMessage.error('请选择患者')
    return
  }

  messageLoading.value = true
  try {
    const response = await axios.post('/api/messages/send', {
      receiver_id: messagePatient.value.id,
      content: messageContent.value.trim()
    })

    if (response.data.success) {
      ElMessage.success('发送成功')
      messageContent.value = ''
      // 刷新聊天记录
      await loadChatHistory(messagePatient.value.id)
    } else {
      ElMessage.error(response.data.error || '发送失败')
    }
  } catch (error) {
    console.error('发送消息失败:', error)
    ElMessage.error(error.response?.data?.error || '发送失败')
  } finally {
    messageLoading.value = false
  }
}

// 获取消息联系人列表
const fetchMessageContacts = async () => {
  contactsLoading.value = true
  try {
    const response = await axios.get('/api/messages/contacts')
    if (response.data.success) {
      messageContacts.value = response.data.contacts || []
      // 计算未读消息总数
      const newUnreadCount = messageContacts.value.reduce((sum, contact) => sum + (contact.unread_count || 0), 0)

      // 如果有新消息，显示通知
      if (newUnreadCount > unreadMessageCount.value && unreadMessageCount.value > 0) {
        ElMessage({
          message: `您有 ${newUnreadCount - unreadMessageCount.value} 条新消息`,
          type: 'info',
          duration: 3000
        })
      }

      unreadMessageCount.value = newUnreadCount
    }
  } catch (error) {
    console.error('获取消息联系人失败:', error)
  } finally {
    contactsLoading.value = false
  }
}

// 消息轮询定时器
let messagePollingTimer = null

// 开始消息轮询
const startMessagePolling = () => {
  // 立即获取一次
  fetchMessageContacts()
  // 每30秒轮询一次
  messagePollingTimer = setInterval(fetchMessageContacts, 30000)
}

// 停止消息轮询
const stopMessagePolling = () => {
  if (messagePollingTimer) {
    clearInterval(messagePollingTimer)
    messagePollingTimer = null
  }
  if (announcementPollingTimer) {
    clearInterval(announcementPollingTimer)
    announcementPollingTimer = null
  }
}

// 获取公告列表
const fetchAnnouncements = async () => {
  try {
    const response = await axios.get('/api/announcements')
    if (response.data.success) {
      announcements.value = response.data.announcements || []
      unreadAnnouncementCount.value = announcements.value.filter(a => !a.is_read).length
    }
  } catch (error) {
    console.error('获取公告失败:', error)
  }
}

// 获取未读公告数量
const fetchUnreadAnnouncementCount = async () => {
  try {
    const response = await axios.get('/api/announcements/unread-count')
    if (response.data.success) {
      unreadAnnouncementCount.value = response.data.unread_count || 0
    }
  } catch (error) {
    console.error('获取未读公告数失败:', error)
  }
}

// 查看公告详情
const viewAnnouncement = async (announcement) => {
  viewingAnnouncement.value = announcement
  announcementDialogVisible.value = true

  // 标记为已读
  if (!announcement.is_read) {
    try {
      await axios.post(`/api/announcements/${announcement.id}/read`)
      announcement.is_read = true
      unreadAnnouncementCount.value = Math.max(0, unreadAnnouncementCount.value - 1)
    } catch (error) {
      console.error('标记公告已读失败:', error)
    }
  }
}

// 获取公告优先级标签
const getAnnouncementPriorityLabel = (priority) => {
  const labels = { low: '低', normal: '普通', high: '高', urgent: '紧急' }
  return labels[priority] || priority
}

// 获取公告优先级类型
const getAnnouncementPriorityType = (priority) => {
  const types = { low: 'info', normal: 'success', high: 'warning', urgent: 'danger' }
  return types[priority] || 'info'
}

// 开始公告轮询
const startAnnouncementPolling = () => {
  fetchAnnouncements()
  announcementPollingTimer = setInterval(fetchAnnouncements, 60000) // 每分钟轮询一次
}

// 公告轮询定时器
let announcementPollingTimer = null

const filteredPatients = computed(() => {
  if (!patientSearch.value) return myPatients.value
  const keyword = patientSearch.value.toLowerCase()
  return myPatients.value.filter(p =>
    p.full_name?.toLowerCase().includes(keyword) ||
    p.patient_number?.toLowerCase().includes(keyword)
  )
})

const filteredRecords = computed(() => {
  if (!recordSearch.value) return medicalRecords.value
  const keyword = recordSearch.value.toLowerCase()
  return medicalRecords.value.filter(r =>
    r.record_number?.toLowerCase().includes(keyword) ||
    r.patient_name?.toLowerCase().includes(keyword)
  )
})

const fetchDoctorData = async () => {
  try {
    const res = await axios.get('/api/doctor/dashboard')
    doctorInfo.value = res.data.doctor || {}
    myPatients.value = res.data.patients || []
    medicalRecords.value = res.data.records || []
    todayRecords.value = res.data.today_records || []
    todayDetections.value = res.data.today_detections || []
    pendingTasks.value = res.data.tasks || []

    // 获取所有患者列表（用于创建病历选择）
    const patientsRes = await axios.get('/api/doctor/all-patients')
    allPatients.value = patientsRes.data.patients || []

    // 获取检查报告列表
    const reportsRes = await axios.get('/api/history')
    detectionReports.value = reportsRes.data.data || []

    // 获取检测历史
    await fetchDetectionHistory()
  } catch (err) {
    console.error('获取医生数据失败:', err)
    ElMessage.error('获取数据失败')
  }
}

// 获取检测历史
const fetchDetectionHistory = async () => {
  historyLoading.value = true
  try {
    const res = await axios.get('/api/history')
    detectionHistory.value = res.data.data || []
  } catch (err) {
    console.error('获取检测历史失败:', err)
    ElMessage.error('获取检测历史失败')
  } finally {
    historyLoading.value = false
  }
}

// 查看检测历史详情
const viewHistoryDetail = (row) => {
  selectedHistory.value = row
  historyDetailVisible.value = true
}

// 删除检测历史
const deleteHistory = async (id) => {
  try {
    await ElMessageBox.confirm('确定要删除这条检测记录吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    await axios.delete(`/api/history/${id}`)
    ElMessage.success('删除成功')
    fetchDetectionHistory()
  } catch (err) {
    if (err !== 'cancel') {
      console.error('删除失败:', err)
      ElMessage.error('删除失败')
    }
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

// 根据置信度获取颜色
const getConfidenceColor = (confidence) => {
  if (confidence >= 0.8) return '#67c23a'
  if (confidence >= 0.6) return '#e6a23c'
  return '#f56c6c'
}

const handleMenuSelect = (index) => { 
  activeMenu.value = index
  // 切换到相关页面时刷新数据
  if (index === 'patients' || index === 'records' || index === 'dashboard') {
    fetchDoctorData()
  }
  // 切换到消息页面时刷新消息列表
  if (index === 'messages') {
    fetchMessageContacts()
  }
}

const handleCommand = (command) => {
  if (command === 'profile') {
    showProfileDialog.value = true
  } else if (command === 'password') {
    showPasswordDialog.value = true
  } else if (command === 'logout') {
    ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning'
    }).then(() => {
      clearAuth()
      router.push('/login')
      ElMessage.success('已退出登录')
    })
  }
}

const searchPatients = () => { /* 搜索逻辑 */ }
const searchRecords = () => { /* 搜索逻辑 */ }

// 查看患者详情
const viewPatient = (row) => {
  selectedPatient.value = row
  patientDetailVisible.value = true
}

// 从患者详情写病历
const writeRecordFromDetail = () => {
  patientDetailVisible.value = false
  newRecord.patient_id = selectedPatient.value.id
  showCreateRecord.value = true
}

const writeRecord = (row) => { newRecord.patient_id = row.id; showCreateRecord.value = true }

const archivePatient = async (row) => {
  const action = row.status === 'active' ? '归档' : '恢复'
  ElMessageBox.confirm(`确定要${action}患者 ${row.full_name} 吗？`, '提示', {
    confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning'
  }).then(async () => {
    try {
      const newStatus = row.status === 'active' ? 'archived' : 'active'
      const res = await axios.put(`/api/doctor/patients/${row.id}/archive`, {
        status: newStatus
      })
      
      if (res.data.success) {
        ElMessage.success(res.data.message)
        // 刷新患者列表
        await fetchDoctorData()
      }
    } catch (err) {
      console.error(`${action}患者失败:`, err)
      ElMessage.error(`${action}失败`)
    }
  })
}

// 查看病历详情
const viewRecord = (row) => {
  selectedRecord.value = row
  recordDetailVisible.value = true
}

const editRecord = (row) => {
  // 填充编辑表单
  editRecordForm.id = row.id
  editRecordForm.patient_id = row.patient_id
  editRecordForm.patient_name = row.patient_name
  editRecordForm.symptoms = row.symptoms || ''
  editRecordForm.diagnosis = row.diagnosis || ''
  editRecordForm.treatment = row.treatment || ''
  editRecordForm.advice = row.advice || ''
  editRecordForm.follow_up_date = row.follow_up_date || ''
  showEditRecord.value = true
}

// 保存编辑的病历
const saveEditRecord = async () => {
  if (!editRecordForm.symptoms || !editRecordForm.diagnosis || !editRecordForm.treatment) {
    ElMessage.warning('请填写必填项')
    return
  }
  
  savingEditRecord.value = true
  try {
    await axios.put(`/api/doctor/medical-records/${editRecordForm.id}`, {
      symptoms: editRecordForm.symptoms,
      diagnosis: editRecordForm.diagnosis,
      treatment: editRecordForm.treatment,
      advice: editRecordForm.advice,
      follow_up_date: editRecordForm.follow_up_date
    })
    ElMessage.success('病历更新成功')
    showEditRecord.value = false
    fetchDoctorData()
  } catch (err) {
    ElMessage.error(err.response?.data?.error || '更新失败')
  } finally {
    savingEditRecord.value = false
  }
}

// 查看检查报告详情
const viewReport = (row) => {
  selectedReport.value = row
  reportDetailVisible.value = true
}

// 编辑医生诊断
const editReport = (row) => {
  editReportForm.value = {
    id: row.id,
    patient_name: row.patient_name || '未知',
    diagnosis: row.diagnosis || '',
    follow_up_notes: row.follow_up_notes || ''
  }
  editReportVisible.value = true
}

// 保存编辑的医生诊断
const saveReportEdit = async () => {
  if (!editReportForm.value) return
  
  savingReport.value = true
  try {
    // 调用后端API保存医生诊断
    const res = await axios.post(`/api/history/${editReportForm.value.id}/advice`, {
      diagnosis: editReportForm.value.diagnosis,
      follow_up_notes: editReportForm.value.follow_up_notes
    })
    
    if (res.data.success) {
      ElMessage.success('医生诊断已保存')
      editReportVisible.value = false
      // 刷新报告列表
      await loadDetectionReports()
    } else {
      ElMessage.error(res.data.error || '保存失败')
    }
  } catch (err) {
    console.error('保存医生诊断失败', err)
    ElMessage.error('保存失败: ' + (err.response?.data?.error || err.message))
  } finally {
    savingReport.value = false
  }
}

// 一键生成医生诊断内容（调用AI API）
const autoFillReport = async () => {
  if (!editReportForm.value) return
  
  // 找到对应的报告数据
  const report = detectionReports.value.find(r => r.id === editReportForm.value.id)
  if (!report || !report.medical_advice || !report.medical_advice.interpretation) {
    ElMessage.warning('暂无AI建议可供参考，请先获取AI建议')
    return
  }
  
  const aiInterpretation = report.medical_advice.interpretation
  const patientName = editReportForm.value.patient_name || '患者'
  
  // 构建prompt，控制AI输出医生诊断格式
  const prompt = `你是一位经验丰富的骨科医生。请根据以下AI辅助诊断建议，生成一份简洁专业的医生诊断结论和随访备注。

AI辅助诊断建议：
${aiInterpretation}

患者姓名：${patientName}

请按以下格式输出，不要添加任何星号或其他特殊符号：

诊断结论：
患者张洋（51岁女性）右膝X线示髌骨远端撕脱性骨折（髌骨上极/股四头肌腱附着点可能），骨片分离移位，属中等严重损伤，伸膝装置完整性受损。建议膝关节伸直位支具固定，需完善CT及MRI评估移位程度及韧带损伤，酌情决定保守或手术治疗。

随访备注：
1. 复查时间：3日内完成膝关节CT+MRI检查；2周后门诊复查X线评估骨片位置，若行保守治疗，4-6周后评估愈合情况
2. 关键注意：严禁屈曲膝关节，拄拐免负重行走；每日检查支具皮肤受压情况，观察足趾血运及感觉
3. 异常处理：如出现患肢肿胀加剧、皮肤发紫或麻木、疼痛难忍等情况，需立即返院就诊

要求：
1. 使用专业但易懂的语言
2. 诊断结论为一段完整文字，不要分点
3. 随访备注使用数字1、2、3分点列出
4. 语气要专业、权威
5. 不要添加任何星号、井号等特殊符号`;

  try {
    ElMessage.info('正在生成医生诊断内容...')
    
    // 60000 是接入 RAG 之前的余量；现在多了一次检索（约 2s）
    // 且带参考资料的回答更长，放宽到 180s
    const res = await axios.post('/api/interpret', {
      detections: report.detections || [],
      prompt: prompt
    }, {
      timeout: 180000
    })
    
    if (res.data.success) {
      const generatedContent = res.data.interpretation
      
      // 解析生成的内容，提取诊断结论和随访备注
      const diagnosisMatch = generatedContent.match(/诊断结论：\s*([\s\S]*?)(?=随访备注：|$)/)
      const followUpMatch = generatedContent.match(/随访备注：\s*([\s\S]*?)$/)
      
      if (diagnosisMatch) {
        editReportForm.value.diagnosis = diagnosisMatch[1].trim()
      } else {
        // 如果没有匹配到格式，使用整个生成内容作为诊断
        editReportForm.value.diagnosis = generatedContent.substring(0, 200) + '...'
      }
      
      if (followUpMatch) {
        editReportForm.value.follow_up_notes = followUpMatch[1].trim()
      } else {
        editReportForm.value.follow_up_notes = '建议定期复查，如有异常及时就医。'
      }
      
      ElMessage.success('已根据AI建议生成医生诊断内容')
    } else {
      ElMessage.error(res.data.error || '生成失败')
    }
  } catch (err) {
    console.error('生成医生诊断内容失败:', err)
    const errorMsg = err.response?.data?.error || err.response?.data?.hint || err.message
    ElMessage.error('生成失败: ' + errorMsg)
    
    // 如果API调用失败，使用默认内容
    editReportForm.value.diagnosis = `根据影像学检查，患者${patientName}显示骨折征象，建议进一步临床评估。`
    editReportForm.value.follow_up_notes = '建议2周后复诊复查，观察骨折愈合情况。如有异常请及时联系主治医师。'
  }
}

// 删除检查报告
const deleteReport = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除报告 #${row.id} 吗？此操作不可恢复！`,
      '确认删除',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    const res = await axios.delete(`/api/history/${row.id}`)
    
    if (res.data.success) {
      ElMessage.success('删除成功')
      // 刷新报告列表
      await loadDetectionReports()
    } else {
      ElMessage.error(res.data.error || '删除失败')
    }
  } catch (err) {
    if (err !== 'cancel') {
      console.error('删除报告失败', err)
      ElMessage.error('删除失败: ' + (err.response?.data?.error || err.message))
    }
  }
}

// 加载检测报告列表（只显示有医生诊断的记录）
const loadDetectionReports = async () => {
  try {
    const res = await axios.get('/api/history')
    // 只显示有医生诊断的记录（diagnosis 或 follow_up_notes 不为空）
    const allData = res.data.data || []
    detectionReports.value = allData.filter(item => 
      item.diagnosis || item.follow_up_notes
    )
  } catch (err) {
    console.error('获取检测报告失败', err)
    ElMessage.error('获取检测报告失败')
  }
}

const startDetection = () => {
  // 根据选择的检测类型跳转到不同的路由
  if (detectType.value === 'image') {
    router.push('/detect')
  } else if (detectType.value === 'video') {
    router.push('/video')
  } else if (detectType.value === 'camera') {
    router.push('/camera')
  } else {
    router.push('/detect')
  }
}

const savePatient = async () => {
  saving.value = true
  try {
    const res = await axios.post('/api/doctor/patients', newPatient)
    // 显示患者登录信息
    ElMessageBox.alert(
      `<div style="padding: 10px;">
        <p><strong>患者添加成功！</strong></p>
        <p style="margin-top: 15px;">请保存以下登录信息提供给患者：</p>
        <div style="background: #f5f5f5; padding: 15px; margin-top: 10px; border-radius: 4px;">
          <p><strong>用户名：</strong>${res.data.username}</p>
          <p><strong>密码：</strong>${res.data.password}</p>
          <p><strong>病历号：</strong>${res.data.patient_number}</p>
        </div>
        <p style="margin-top: 15px; color: #666; font-size: 12px;">患者可使用用户名和密码在患者端登录查看病历</p>
      </div>`,
      '患者登录信息',
      {
        dangerouslyUseHTMLString: true,
        confirmButtonText: '已保存',
        type: 'success'
      }
    )
    resetPatientForm()
    fetchDoctorData()
  } catch (err) {
    ElMessage.error(err.response?.data?.error || '添加失败')
  } finally {
    saving.value = false
  }
}

const resetPatientForm = () => {
  Object.keys(newPatient).forEach(key => {
    newPatient[key] = key === 'gender' ? '男' : ''
  })
}

// 生成随机手机号
const generatePhone = () => {
  const prefixes = ['138', '139', '137', '136', '135', '134', '159', '158', '157', '150', '151', '152', '188', '187', '182', '181']
  const prefix = prefixes[Math.floor(Math.random() * prefixes.length)]
  const suffix = Math.floor(Math.random() * 100000000).toString().padStart(8, '0')
  return prefix + suffix
}

// 生成随机身份证号
const generateIdCard = () => {
  const prefix = '110101'
  const year = Math.floor(Math.random() * (2000 - 1960) + 1960).toString()
  const month = Math.floor(Math.random() * 12 + 1).toString().padStart(2, '0')
  const day = Math.floor(Math.random() * 28 + 1).toString().padStart(2, '0')
  const suffix = Math.floor(Math.random() * 10000).toString().padStart(4, '0')
  return prefix + year + month + day + suffix
}

// 生成随机日期
const generateDate = (startYear, endYear) => {
  const year = Math.floor(Math.random() * (endYear - startYear) + startYear)
  const month = Math.floor(Math.random() * 12 + 1).toString().padStart(2, '0')
  const day = Math.floor(Math.random() * 28 + 1).toString().padStart(2, '0')
  return `${year}-${month}-${day}`
}

// 患者姓名库
const patientNames = ['张伟', '李娜', '王芳', '刘洋', '陈静', '杨帆', '赵敏', '黄磊', '周杰', '吴倩', '徐丽', '孙强', '马超', '朱琳', '胡军', '郭明', '何欣', '高远', '林峰', '郑雨']

// 一键生成患者信息
const autoFillPatient = () => {
  const randomName = patientNames[Math.floor(Math.random() * patientNames.length)]
  const randomGender = Math.random() > 0.5 ? '男' : '女'
  
  newPatient.full_name = randomName
  newPatient.id_card = generateIdCard()
  newPatient.gender = randomGender
  newPatient.birth_date = generateDate(1960, 2000)
  newPatient.phone = generatePhone()
  newPatient.address = '北京市朝阳区' + Math.floor(Math.random() * 100) + '号院' + Math.floor(Math.random() * 20) + '号楼'
  newPatient.emergency_contact = '家属' + randomName[0]
  newPatient.emergency_phone = generatePhone()
  newPatient.allergies = '无'
  newPatient.medical_history = '无特殊病史'
  
  ElMessage.success('已自动生成患者信息')
}

const changePassword = async () => {
  if (!passwordForm.oldPassword || !passwordForm.newPassword || !passwordForm.confirmPassword) {
    ElMessage.warning('请填写所有密码字段')
    return
  }
  if (passwordForm.newPassword !== passwordForm.confirmPassword) {
    ElMessage.error('两次输入的新密码不一致')
    return
  }
  if (passwordForm.newPassword.length < 6) {
    ElMessage.error('新密码至少6位')
    return
  }
  try {
    await axios.post('/api/change-password', {
      old_password: passwordForm.oldPassword,
      new_password: passwordForm.newPassword
    })
    ElMessage.success('密码修改成功')
    showPasswordDialog.value = false
    passwordForm.oldPassword = ''
    passwordForm.newPassword = ''
    passwordForm.confirmPassword = ''
  } catch (err) {
    ElMessage.error(err.response?.data?.error || '修改失败')
  }
}

const openEditProfile = () => {
  // 填充表单数据
  editProfileForm.full_name = doctorInfo.value.full_name || ''
  editProfileForm.phone = doctorInfo.value.phone || ''
  editProfileForm.email = doctorInfo.value.email || ''
  editProfileForm.hospital = doctorInfo.value.hospital || ''
  editProfileForm.department = doctorInfo.value.department || ''
  editProfileForm.title = doctorInfo.value.title || ''
  editProfileForm.license_number = doctorInfo.value.license_number || ''
  editProfileForm.specialty = doctorInfo.value.specialty || ''
  
  showProfileDialog.value = false
  showEditProfileDialog.value = true
}

const saveProfile = async () => {
  // 表单验证
  if (!editProfileForm.full_name.trim()) {
    ElMessage.warning('请输入真实姓名')
    return
  }
  if (editProfileForm.phone && !/^1[3-9]\d{9}$/.test(editProfileForm.phone)) {
    ElMessage.warning('手机号格式不正确')
    return
  }
  
  savingProfile.value = true
  try {
    await axios.put('/api/profile/update', editProfileForm)
    ElMessage.success('个人信息更新成功')
    showEditProfileDialog.value = false
    fetchDoctorData() // 刷新数据
  } catch (err) {
    ElMessage.error(err.response?.data?.error || '更新失败')
  } finally {
    savingProfile.value = false
  }
}

// 一键生成病历信息
const autoFillRecord = () => {
  // 如果没有选择患者，自动选择第一个
  if (!newRecord.patient_id && allPatients.value.length > 0) {
    newRecord.patient_id = allPatients.value[0].id
  }
  
  const symptomsList = [
    '患者自述腰部疼痛，活动受限，行走困难，伴有下肢麻木感',
    '右膝关节肿胀疼痛，屈伸活动受限，行走时疼痛加重',
    '左肩部疼痛，抬举困难，夜间疼痛明显，影响睡眠',
    '颈椎不适，头晕头痛，上肢麻木，颈部活动受限',
    '腰部扭伤后疼痛，不能弯腰，咳嗽时疼痛加重'
  ]
  
  const diagnosisList = [
    '腰椎间盘突出症',
    '右膝关节骨性关节炎',
    '左肩袖损伤',
    '颈椎病（神经根型）',
    '急性腰扭伤'
  ]
  
  const treatmentList = [
    '1. 卧床休息，腰部制动\n2. 口服非甾体抗炎药\n3. 物理治疗（热敷、牵引）\n4. 必要时行微创手术治疗',
    '1. 关节腔内注射玻璃酸钠\n2. 口服氨基葡萄糖\n3. 膝关节功能锻炼\n4. 避免剧烈运动',
    '1. 肩关节制动\n2. 口服消炎止痛药\n3. 局部封闭治疗\n4. 康复训练',
    '1. 颈椎牵引治疗\n2. 口服营养神经药物\n3. 颈部功能锻炼\n4. 避免长时间低头',
    '1. 卧床休息\n2. 局部热敷\n3. 口服止痛药\n4. 腰背肌功能锻炼'
  ]
  
  const adviceList = [
    '注意休息，避免久坐久站，适当进行腰背肌锻炼，定期复查',
    '控制体重，避免爬楼梯和深蹲，注意膝关节保暖',
    '避免提重物，循序渐进进行肩关节功能锻炼',
    '保持正确坐姿，使用合适高度的枕头，避免颈部受凉',
    '急性期过后逐步恢复活动，加强腰背肌锻炼预防复发'
  ]
  
  const randomIndex = Math.floor(Math.random() * symptomsList.length)
  
  newRecord.symptoms = symptomsList[randomIndex]
  newRecord.diagnosis = diagnosisList[randomIndex]
  newRecord.treatment = treatmentList[randomIndex]
  newRecord.advice = adviceList[randomIndex]
  newRecord.follow_up_date = generateDate(2025, 2026)
  
  ElMessage.success('已自动生成病历信息')
}

// 一键生成个人资料
const autoFillProfile = () => {
  const hospitals = ['北京协和医院', '301医院', '北京大学人民医院', '北京积水潭医院', '中日友好医院']
  const departments = ['骨科', '脊柱外科', '关节外科', '创伤骨科', '运动医学科']
  const titles = ['住院医师', '主治医师', '副主任医师', '主任医师']
  
  editProfileForm.full_name = doctorInfo.value.full_name || '王医生'
  editProfileForm.phone = generatePhone()
  editProfileForm.email = 'doctor' + Math.floor(Math.random() * 100000) + '@hospital.com'
  editProfileForm.hospital = hospitals[Math.floor(Math.random() * hospitals.length)]
  editProfileForm.department = departments[Math.floor(Math.random() * departments.length)]
  editProfileForm.title = titles[Math.floor(Math.random() * titles.length)]
  editProfileForm.license_number = '110' + Math.floor(Math.random() * 1000000000000).toString().padStart(12, '0')
  editProfileForm.specialty = '擅长骨折诊断、关节置换、脊柱手术等骨科疾病的诊治，具有丰富的临床经验'
  
  ElMessage.success('已自动生成个人资料')
}

const saveRecord = async () => {
  savingRecord.value = true
  try {
    await axios.post('/api/doctor/medical-records', newRecord)
    ElMessage.success('病历创建成功')
    showCreateRecord.value = false
    fetchDoctorData()
  } catch (err) {
    ElMessage.error(err.response?.data?.error || '创建失败')
  } finally {
    savingRecord.value = false
  }
}

onMounted(() => {
  fetchDoctorData()
  startMessagePolling()
  startAnnouncementPolling()
})

onUnmounted(() => {
  stopMessagePolling()
})
</script>

<style scoped>
.doctor-workstation { min-height: 100vh; background: #f5f7fa; }
.workstation-header {
  display: flex; align-items: center; justify-content: space-between;
  background: white; border-bottom: 1px solid #e4e7ed; padding: 0 30px; height: 64px;
}
.header-left { display: flex; align-items: center; gap: 12px; }
.system-name { font-size: 20px; font-weight: 600; color: #1e293b; }
.header-right { display: flex; align-items: center; gap: 16px; }
.welcome-text { color: #64748b; }
.user-avatar { cursor: pointer; }
.workstation-container { height: calc(100vh - 64px); }
.workstation-sidebar { background: white; border-right: 1px solid #e4e7ed; }
.workstation-menu { border-right: none; padding: 20px 0; }
.workstation-main { padding: 30px; overflow-y: auto; }
.page-title { margin-bottom: 24px; color: #1e293b; font-size: 24px; font-weight: 600; }
.stat-cards { margin-bottom: 24px; }
.stat-card { height: 100%; }
.stat-card :deep(.el-card__body) { display: flex; align-items: center; padding: 24px; }
.stat-icon { width: 60px; height: 60px; border-radius: 12px; display: flex; align-items: center; justify-content: center; margin-right: 16px; }
.stat-icon.blue { background: #dbeafe; color: #3b82f6; }
.stat-icon.green { background: #d1fae5; color: #10b981; }
.stat-icon.orange { background: #ffedd5; color: #f97316; }
.stat-icon.purple { background: #f3e8ff; color: #a855f7; }
.stat-number { font-size: 28px; font-weight: 700; color: #1e293b; }
.stat-label { color: #64748b; font-size: 14px; }
.quick-actions { margin-bottom: 24px; }
.action-buttons { display: flex; gap: 16px; }

/* 消息徽章样式 */
.message-badge-menu {
  margin-left: 16px;
  position: relative;
  display: inline-flex;
  align-items: center;
}

.message-badge-menu :deep(.el-badge__content) {
  position: absolute;
  top: -8px;
  right: -12px;
  transform: translate(0, 0);
  border: none;
}
.todo-list { margin-top: 24px; }
.table-header { display: flex; justify-content: space-between; margin-bottom: 16px; }
.detect-options { text-align: center; margin-bottom: 40px; }
.detect-content { text-align: center; padding: 60px 0; }
.detect-hint { color: #64748b; margin-bottom: 24px; }
</style>
