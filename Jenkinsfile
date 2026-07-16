pipeline {
  agent { label 'docker' }

  options {
    disableConcurrentBuilds()
    skipDefaultCheckout(true)
    timestamps()
    timeout(time: 45, unit: 'MINUTES')
    buildDiscarder(logRotator(numToKeepStr: '20'))
  }

  environment {
    DOCKER_BUILDKIT = '1'
  }

  stages {
    stage('Checkout') {
      steps {
        script {
          def scmVars = checkout scm
          env.COMMIT_SHA = sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
          env.SCM_BRANCH = scmVars.GIT_BRANCH ?: sh(
            script: 'git rev-parse --abbrev-ref HEAD', returnStdout: true
          ).trim()
          echo "SCM_BRANCH=${env.SCM_BRANCH} BRANCH_NAME=${env.BRANCH_NAME ?: ''} " +
               "CHANGE_ID=${env.CHANGE_ID ?: ''} COMMIT_SHA=${env.COMMIT_SHA}"
        }
      }
    }

    stage('Tests and production builds') {
      steps {
        script {
          withEnv([
            "API_IMAGE=financial-freedom-api:${env.COMMIT_SHA}",
            "UI_IMAGE=financial-freedom-ui:${env.COMMIT_SHA}"
          ]) {
            sh 'chmod +x scripts/ci/*.sh && scripts/ci/test.sh'
          }
        }
      }
      post {
        always {
          junit allowEmptyResults: true, testResults: 'test-results/**/*-junit.xml'
          archiveArtifacts allowEmptyArchive: true, artifacts: 'test-results/**/*', fingerprint: true
        }
      }
    }

    stage('Deploy production') {
      when {
        expression {
          def branch = env.BRANCH_NAME ?: env.SCM_BRANCH ?: ''
          return !env.CHANGE_ID && branch in ['main', 'origin/main', 'refs/heads/main']
        }
      }
      steps {
        script {
          withCredentials([file(
            credentialsId: 'financial-freedom-production-env',
            variable: 'DEPLOY_ENV_FILE'
          )]) {
            withEnv([
              "API_IMAGE=financial-freedom-api:${env.COMMIT_SHA}",
              "UI_IMAGE=financial-freedom-ui:${env.COMMIT_SHA}"
            ]) {
              sh 'scripts/ci/deploy.sh'
            }
          }
        }
      }
    }
  }

  post {
    always {
      sh 'docker image prune -f --filter "until=168h" || true'
      deleteDir()
    }
  }
}
